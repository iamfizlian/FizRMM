from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .bootstrap import render_windows_bootstrap
from .models import AccessDenied, NotFound, TenantContext, to_jsonable
from .store import InMemoryControlPlaneStore, seed_store


def default_store() -> InMemoryControlPlaneStore:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from .db_store import PostgresControlPlaneStore

        return PostgresControlPlaneStore(database_url)  # type: ignore[return-value]
    return seed_store()


STORE = default_store()


@dataclass(frozen=True)
class TextResponse:
    body: str
    content_type: str = "text/plain; charset=utf-8"


def deployment_config() -> dict[str, object]:
    return {
        "portal_url": os.getenv("FIZRMM_PUBLIC_URL", "http://127.0.0.1:8000"),
        "meshcentral": {
            "server_url": os.getenv("MESHCENTRAL_URL", ""),
            "installer_url": os.getenv("MESHCENTRAL_AGENT_INSTALLER_URL", ""),
            "install_args": os.getenv("MESHCENTRAL_AGENT_INSTALL_ARGS", ""),
        },
        "zabbix": {
            "server_url": os.getenv("ZABBIX_SERVER", ""),
            "installer_url": os.getenv("ZABBIX_AGENT_INSTALLER_URL", ""),
            "install_args": os.getenv("ZABBIX_AGENT_INSTALL_ARGS", ""),
        },
        "wazuh": {
            "manager_url": os.getenv("WAZUH_MANAGER", ""),
            "installer_url": os.getenv("WAZUH_AGENT_INSTALLER_URL", ""),
            "install_args": os.getenv("WAZUH_AGENT_INSTALL_ARGS", ""),
        },
        "salt": {
            "master_url": os.getenv("SALT_MASTER", ""),
            "installer_url": os.getenv("SALT_MINION_INSTALLER_URL", ""),
            "install_args": os.getenv("SALT_MINION_INSTALL_ARGS", ""),
        },
    }


def context_from_headers(headers: Any) -> TenantContext:
    role = headers.get("X-FizRMM-Role", "technician")
    org_header = headers.get("X-FizRMM-Orgs", "org_acme")
    org_ids = tuple(org.strip() for org in org_header.split(",") if org.strip())
    return TenantContext(
        user_id=headers.get("X-FizRMM-User", "demo-tech"),
        allowed_org_ids=org_ids,
        role=role,
        platform_admin=role == "platform-admin",
    )


class FizRmmHandler(BaseHTTPRequestHandler):
    server_version = "FizRMMDev/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        self._handle(lambda context, parts: self._route_get(context, parts))

    def do_POST(self) -> None:
        self._handle(lambda context, parts: self._route_post(context, parts))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle(self, router: Any) -> None:
        context = context_from_headers(self.headers)
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        try:
            payload = router(context, parts)
            if isinstance(payload, TextResponse):
                self._send_text(payload.body, payload.content_type)
            else:
                self._send_json(payload)
        except NotFound as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except AccessDenied as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.FORBIDDEN)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _route_get(self, context: TenantContext, parts: list[str]) -> Any:
        if parts == ["health"]:
            return {"status": "ok", "service": "fizrmm-api", **STORE.health()}
        if parts == ["api", "orgs"]:
            return {"organizations": STORE.list_organizations(context)}
        if parts == ["api", "assets"]:
            return {"assets": STORE.list_assets(context)}
        if len(parts) == 3 and parts[:2] == ["api", "assets"]:
            asset_id = parts[2]
            return {
                "asset": STORE.get_asset(context, asset_id),
                "connectors": STORE.list_connectors(context, asset_id),
            }
        if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "agents":
            return {"agents": STORE.list_agent_health(context, parts[2])}
        if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "timeline":
            return {"events": STORE.list_timeline(context, parts[2])}
        if parts == ["api", "scripts"]:
            return {"scripts": STORE.list_scripts(context)}
        if len(parts) == 4 and parts[:2] == ["api", "enrollments"] and parts[3] == "bootstrap.ps1":
            enrollment = STORE.get_enrollment_by_token(parts[2])
            portal_url = str(enrollment.config.get("portal_url") or deployment_config()["portal_url"])
            return TextResponse(render_windows_bootstrap(portal_url, parts[2]), "text/plain; charset=utf-8")
        raise NotFound("route not found")

    def _route_post(self, context: TenantContext, parts: list[str]) -> Any:
        if parts == ["api", "enrollments"]:
            payload = self._read_payload()
            expires_hours = int(payload.get("expires_hours", 24))
            expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)
            return STORE.create_enrollment(
                context=context,
                org_id=payload.get("org_id", context.allowed_org_ids[0] if context.allowed_org_ids else ""),
                site=payload.get("site", "Default"),
                config=deployment_config(),
                expires_at=expires_at.isoformat(),
            )
        if len(parts) == 4 and parts[:2] == ["api", "enrollments"] and parts[3] == "claim":
            payload = self._read_payload()
            return STORE.claim_enrollment(
                token=parts[2],
                hostname=payload.get("hostname", "unknown"),
                operating_system=payload.get("operating_system", "unknown"),
            )
        if len(parts) == 4 and parts[:2] == ["api", "enrollments"] and parts[3] == "report":
            payload = self._read_payload()
            return STORE.report_enrollment(
                token=parts[2],
                agents=payload.get("agents", []),
            )
        if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "remote-sessions":
            payload = self._read_payload()
            return STORE.create_remote_session(
                context=context,
                asset_id=parts[2],
                engine=payload.get("engine", "meshcentral"),
            )
        if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "script-runs":
            payload = self._read_payload()
            return STORE.create_script_run(
                context=context,
                asset_id=parts[2],
                script_id=payload.get("script_id", ""),
            )
        raise NotFound("route not found")

    def _read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(to_jsonable(payload), indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FizRMM-User, X-FizRMM-Orgs, X-FizRMM-Role")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, body_text: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = body_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-FizRMM-User, X-FizRMM-Orgs, X-FizRMM-Role")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)


def make_server(
    host: str,
    port: int,
    store: InMemoryControlPlaneStore | None = None,
) -> ThreadingHTTPServer:
    global STORE
    if store is not None:
        STORE = store
    return ThreadingHTTPServer((host, port), FizRmmHandler)


def run_dev_server(host: str | None = None, port: int | None = None) -> None:
    host = host or os.getenv("FIZRMM_HOST", "127.0.0.1")
    port = port or int(os.getenv("FIZRMM_PORT", "8000"))
    server = make_server(host, port)
    print(f"FizRMM API listening on http://{host}:{port}")
    server.serve_forever()
