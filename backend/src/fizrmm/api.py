from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from .auth import context_from_authorization
from .bootstrap import render_linux_bootstrap, render_windows_bootstrap
from .integrations.config import load_runtime_config, runtime_bootstrap_value, runtime_service_value, save_runtime_integration
from .integrations.setup_tasks import run_runtime_setup
from .models import AccessDenied, NotFound, TenantContext, ValidationError, to_jsonable
from .store import InMemoryControlPlaneStore, seed_store


def request_base_url(headers: Any) -> str:
    forwarded_host = str(headers.get("X-Forwarded-Host") or "").split(",", 1)[0].strip()
    host = forwarded_host or str(headers.get("Host") or "").split(",", 1)[0].strip()
    if not host:
        return ""
    proto = str(headers.get("X-Forwarded-Proto") or "http").split(",", 1)[0].strip() or "http"
    return f"{proto}://{host}".rstrip("/")


def is_local_or_internal_url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    hostname = (parsed.hostname or "").lower()
    return hostname in {"", "localhost", "127.0.0.1", "0.0.0.0", "api"}


def public_portal_url(headers: Any, stored_url: object = "") -> str:
    explicit = os.getenv("FIZRMM_PUBLIC_URL", "").strip().rstrip("/")
    if explicit and not is_local_or_internal_url(explicit):
        return explicit
    request_url = request_base_url(headers)
    if request_url and (not stored_url or is_local_or_internal_url(stored_url)):
        return request_url
    return str(stored_url or request_url or deployment_config()["portal_url"]).rstrip("/")


def env_value(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def public_url_with_port(base_url: str, port: int, scheme: str = "https") -> str:
    parsed = urlparse(base_url)
    if not parsed.hostname:
        return ""
    netloc = parsed.hostname
    if ":" in netloc and not netloc.startswith("["):
        netloc = f"[{netloc}]"
    return urlunparse((scheme, f"{netloc}:{port}", "", "", "", "")).rstrip("/")


def public_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.hostname or ""


def meshcentral_public_url(portal_url: str) -> str:
    explicit = os.getenv("MESHCENTRAL_PUBLIC_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    service_url = os.getenv("MESHCENTRAL_URL", "").strip().rstrip("/")
    if service_url and not is_local_or_internal_url(service_url):
        return service_url
    return public_url_with_port(portal_url, int(os.getenv("MESHCENTRAL_PUBLIC_PORT", "8443")), "https")


def meshcentral_mesh_id(default: str = "") -> str:
    return runtime_bootstrap_value("meshcentral", "mesh_id", env_value("MESHCENTRAL_MESH_ID", default)).strip()


def meshcentral_installer_defaults(portal_url: str, mesh_id: str = "") -> dict[str, str]:
    public_url = meshcentral_public_url(portal_url)
    resolved_mesh_id = (mesh_id or meshcentral_mesh_id()).strip()
    defaults = {
        "mesh_id": resolved_mesh_id,
        "linux_installer_url": "",
        "linux_install_args": "",
        "linux_insecure_tls": "false",
        "installer_url": "",
        "install_args": "",
    }
    if not public_url:
        return defaults
    if not resolved_mesh_id:
        defaults.update(
            {
                "linux_installer_url": f"{public_url}/meshagents?id=6&installflags=0",
                "linux_install_args": '"$INSTALLER_PATH" -install',
                "linux_insecure_tls": env_value("MESHCENTRAL_LINUX_INSECURE_TLS", "true"),
                "installer_url": f"{public_url}/meshagents?id=4&installflags=0",
                "install_args": "{INSTALLER_PATH} -fullinstall",
            }
        )
        return defaults
    encoded_mesh_id = quote(resolved_mesh_id, safe="")
    defaults.update(
        {
            "linux_installer_url": f"{public_url}/meshagents?id=6&meshid={encoded_mesh_id}&installflags=0",
            "linux_install_args": '"$INSTALLER_PATH" -install',
            "linux_insecure_tls": env_value("MESHCENTRAL_LINUX_INSECURE_TLS", "true"),
            "installer_url": f"{public_url}/meshagents?id=4&meshid={encoded_mesh_id}&installflags=0",
            "install_args": "{INSTALLER_PATH} -fullinstall",
        }
    )
    return defaults


def apply_meshcentral_agent_defaults(config: dict[str, object], portal_url: str) -> None:
    meshcentral = config.get("meshcentral")
    if not isinstance(meshcentral, dict):
        return
    mesh_id = str(meshcentral.get("mesh_id") or meshcentral_mesh_id()).strip()
    meshcentral["mesh_id"] = mesh_id
    defaults = meshcentral_installer_defaults(portal_url, mesh_id)
    for key, value in defaults.items():
        meshcentral[key] = str(meshcentral.get(key) or value)
    meshcentral["server_url"] = str(meshcentral.get("server_url") or meshcentral_public_url(portal_url))


def meshcentral_agent_required_by_runtime() -> bool:
    configured = os.getenv("FIZRMM_REQUIRE_MESHCENTRAL_AGENT", "false").strip().lower()
    if configured in {"0", "false", "no", "off"}:
        return False
    return True


def require_meshcentral_agent_config(config: dict[str, object]) -> None:
    if not meshcentral_agent_required_by_runtime():
        return
    meshcentral = config.get("meshcentral")
    if not isinstance(meshcentral, dict):
        raise ValidationError("MeshCentral deployment config is missing")
    if str(meshcentral.get("linux_installer_url") or "").strip():
        return
    raise ValidationError(
        "MeshCentral Linux agent installer is required for enrollment. "
        "Set MESHCENTRAL_MESH_ID after creating a MeshCentral device group, or set "
        "MESHCENTRAL_LINUX_AGENT_INSTALLER_URL explicitly."
    )

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


BUNDLED_SERVICE_URLS = {
    "identity": "http://keycloak:8080",
    "meshcentral": "https://meshcentral:443",
    "zabbix": "http://zabbix-web:8080/api_jsonrpc.php",
    "wazuh": "https://wazuh-manager:55000",
    "salt": "tcp://salt-master:4505",
    "opensearch": "https://opensearch:9200",
    "nats": "nats://nats:4222",
}

BUNDLED_BOOTSTRAP_DEFAULTS = {
    "zabbix_server": "zabbix-server",
    "wazuh_manager": "wazuh-manager",
    "salt_master": "salt-master",
}

INTEGRATION_SETUP_STEPS = {
    "identity": [
        "Run the Keycloak container/profile or point KEYCLOAK_URL at an existing Keycloak instance.",
        "Create/configure the FizRMM realm and OIDC client, then set OIDC_CLIENT_ID and issuer/JWKS settings if they differ from bundled defaults.",
    ],
    "meshcentral": [
        "Run or connect a MeshCentral server reachable by endpoints; set MESHCENTRAL_PUBLIC_URL when it is not https://<portal-host>:8443.",
        "Create a MeshCentral device group for the tenant/site and copy its mesh/... identifier into MESHCENTRAL_MESH_ID, or provide MESHCENTRAL_LINUX_AGENT_INSTALLER_URL directly.",
        "Create new endpoint enrollments after the MeshCentral mesh ID/installer URL is configured so the bootstrap can install the remote-control agent.",
    ],
    "zabbix": [
        "Run or connect Zabbix server/web and make TCP 10051 reachable from enrolled endpoints.",
        "Confirm ZABBIX_SERVER points to the endpoint-reachable Zabbix server/proxy address; the Linux bootstrap installs/configures zabbix-agent2 when no explicit installer URL is set.",
        "Configure host auto-registration/templates in Zabbix for newly enrolled endpoints.",
    ],
    "wazuh": [
        "Run or connect a Wazuh manager and make enrollment/agent ports 1514 and 1515 reachable from enrolled endpoints.",
        "Confirm WAZUH_MANAGER points to the endpoint-reachable Wazuh manager; the Linux bootstrap installs the official wazuh-agent package when no explicit installer URL is set.",
        "Configure Wazuh enrollment/auth settings for the agent groups you expect FizRMM endpoints to join.",
    ],
    "salt": [
        "Run or connect a Salt master and make ports 4505/4506 reachable from enrolled endpoints.",
        "Confirm SALT_MASTER points to the endpoint-reachable Salt master; the Linux bootstrap installs/configures salt-minion when no explicit installer URL is set.",
        "Accept or preseed minion keys for enrolled endpoints on the Salt master.",
    ],
    "opensearch": [
        "Run or connect OpenSearch and set OPENSEARCH_URL when it differs from the bundled service URL.",
        "Configure index templates/retention and connect Wazuh or log ingestion before treating search as production-ready.",
    ],
    "nats": [
        "Run or connect NATS JetStream and set NATS_URL when it differs from the bundled service URL.",
        "Create streams/consumers used by automation workers before treating messaging as production-ready.",
    ],
}


INTEGRATION_SETUP_FIELDS = {
    "identity": {"service": {"url", "public_url", "realm", "client_id", "issuer_url", "jwks_url"}, "bootstrap": set()},
    "meshcentral": {"service": {"url", "public_url"}, "bootstrap": {"server_url", "mesh_id", "linux_installer_url", "linux_install_args", "linux_insecure_tls", "installer_url", "install_args"}},
    "zabbix": {"service": {"url"}, "bootstrap": {"server_url", "linux_installer_url", "linux_install_args", "installer_url", "install_args"}},
    "wazuh": {"service": {"url"}, "bootstrap": {"manager_url", "linux_installer_url", "linux_install_args", "installer_url", "install_args"}},
    "salt": {"service": {"api_url", "url"}, "bootstrap": {"master_url", "linux_installer_url", "linux_install_args", "installer_url", "install_args"}},
    "opensearch": {"service": {"url"}, "bootstrap": set()},
    "nats": {"service": {"url"}, "bootstrap": set()},
}


def deployment_config() -> dict[str, object]:
    portal_url = env_value("FIZRMM_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
    endpoint_host = public_host(portal_url)
    meshcentral_defaults = meshcentral_installer_defaults(portal_url)
    meshcentral_url = meshcentral_public_url(portal_url)
    return {
        "portal_url": portal_url,
        "meshcentral": {
            "mesh_id": runtime_bootstrap_value("meshcentral", "mesh_id", env_value("MESHCENTRAL_MESH_ID", meshcentral_defaults["mesh_id"])),
            "server_url": runtime_bootstrap_value("meshcentral", "server_url", env_value("MESHCENTRAL_URL", meshcentral_url)),
            "installer_url": runtime_bootstrap_value(
                "meshcentral",
                "installer_url",
                env_value("MESHCENTRAL_AGENT_INSTALLER_URL", meshcentral_defaults["installer_url"]),
            ),
            "install_args": runtime_bootstrap_value(
                "meshcentral",
                "install_args",
                env_value("MESHCENTRAL_AGENT_INSTALL_ARGS", meshcentral_defaults["install_args"]),
            ),
            "linux_installer_url": runtime_bootstrap_value(
                "meshcentral",
                "linux_installer_url",
                env_value("MESHCENTRAL_LINUX_AGENT_INSTALLER_URL", meshcentral_defaults["linux_installer_url"]),
            ),
            "linux_install_args": runtime_bootstrap_value(
                "meshcentral",
                "linux_install_args",
                env_value("MESHCENTRAL_LINUX_AGENT_INSTALL_ARGS", meshcentral_defaults["linux_install_args"]),
            ),
            "linux_insecure_tls": runtime_bootstrap_value(
                "meshcentral",
                "linux_insecure_tls",
                env_value("MESHCENTRAL_LINUX_INSECURE_TLS", meshcentral_defaults["linux_insecure_tls"]),
            ),
        },
        "zabbix": {
            "server_url": runtime_bootstrap_value("zabbix", "server_url", env_value("ZABBIX_SERVER", endpoint_host or BUNDLED_BOOTSTRAP_DEFAULTS["zabbix_server"])),
            "installer_url": runtime_bootstrap_value(
                "zabbix",
                "installer_url",
                env_value("ZABBIX_AGENT_INSTALLER_URL"),
            ),
            "install_args": runtime_bootstrap_value(
                "zabbix",
                "install_args",
                env_value("ZABBIX_AGENT_INSTALL_ARGS"),
            ),
            "linux_installer_url": runtime_bootstrap_value(
                "zabbix",
                "linux_installer_url",
                env_value("ZABBIX_LINUX_AGENT_INSTALLER_URL"),
            ),
            "linux_install_args": runtime_bootstrap_value(
                "zabbix",
                "linux_install_args",
                env_value("ZABBIX_LINUX_AGENT_INSTALL_ARGS"),
            ),
        },
        "wazuh": {
            "manager_url": runtime_bootstrap_value("wazuh", "manager_url", env_value("WAZUH_MANAGER", endpoint_host or BUNDLED_BOOTSTRAP_DEFAULTS["wazuh_manager"])),
            "installer_url": runtime_bootstrap_value(
                "wazuh",
                "installer_url",
                env_value("WAZUH_AGENT_INSTALLER_URL"),
            ),
            "install_args": runtime_bootstrap_value("wazuh", "install_args", env_value("WAZUH_AGENT_INSTALL_ARGS")),
            "linux_installer_url": runtime_bootstrap_value(
                "wazuh",
                "linux_installer_url",
                env_value("WAZUH_LINUX_AGENT_INSTALLER_URL"),
            ),
            "linux_install_args": runtime_bootstrap_value(
                "wazuh",
                "linux_install_args",
                env_value("WAZUH_LINUX_AGENT_INSTALL_ARGS"),
            ),
        },
        "salt": {
            "master_url": runtime_bootstrap_value("salt", "master_url", env_value("SALT_MASTER", endpoint_host or BUNDLED_BOOTSTRAP_DEFAULTS["salt_master"])),
            "installer_url": runtime_bootstrap_value(
                "salt",
                "installer_url",
                env_value("SALT_MINION_INSTALLER_URL"),
            ),
            "install_args": runtime_bootstrap_value("salt", "install_args", env_value("SALT_MINION_INSTALL_ARGS")),
            "linux_installer_url": runtime_bootstrap_value(
                "salt",
                "linux_installer_url",
                env_value("SALT_LINUX_MINION_INSTALLER_URL"),
            ),
            "linux_install_args": runtime_bootstrap_value(
                "salt",
                "linux_install_args",
                env_value("SALT_LINUX_MINION_INSTALL_ARGS"),
            ),
        },
    }


def integration_setup_defaults(integration_id: str, config: dict[str, object]) -> dict[str, dict[str, str]]:
    portal_url = str(config.get("portal_url") or env_value("FIZRMM_PUBLIC_URL", "http://127.0.0.1:8000"))
    service_url = BUNDLED_SERVICE_URLS.get(integration_id, "")
    service: dict[str, str] = {}
    bootstrap: dict[str, str] = {}
    if integration_id == "identity":
        service = {
            "url": BUNDLED_SERVICE_URLS["identity"],
            "public_url": env_value("KEYCLOAK_PUBLIC_URL", "http://127.0.0.1:8080"),
            "realm": env_value("KEYCLOAK_REALM", "fizrmm"),
            "client_id": env_value("OIDC_CLIENT_ID", "fizrmm-portal"),
            "issuer_url": env_value("KEYCLOAK_ISSUER", "http://127.0.0.1:8080/realms/fizrmm"),
            "jwks_url": env_value("KEYCLOAK_JWKS_URL", "http://127.0.0.1:8080/realms/fizrmm/protocol/openid-connect/certs"),
        }
    elif integration_id == "meshcentral":
        meshcentral = config.get("meshcentral", {})
        mesh_values = meshcentral if isinstance(meshcentral, dict) else {}
        public_url = meshcentral_public_url(portal_url)
        service = {"url": service_url, "public_url": public_url}
        bootstrap = {
            "server_url": str(mesh_values.get("server_url") or public_url),
            "mesh_id": str(mesh_values.get("mesh_id") or ""),
            "linux_installer_url": str(mesh_values.get("linux_installer_url") or ""),
            "linux_install_args": str(mesh_values.get("linux_install_args") or '"$INSTALLER_PATH" -install'),
            "linux_insecure_tls": str(mesh_values.get("linux_insecure_tls") or "true"),
        }
    elif integration_id == "zabbix":
        zabbix = config.get("zabbix", {})
        values = zabbix if isinstance(zabbix, dict) else {}
        service = {"url": service_url}
        bootstrap = {"server_url": str(values.get("server_url") or public_host(portal_url) or "zabbix-server")}
    elif integration_id == "wazuh":
        wazuh = config.get("wazuh", {})
        values = wazuh if isinstance(wazuh, dict) else {}
        service = {"url": service_url}
        bootstrap = {"manager_url": str(values.get("manager_url") or public_host(portal_url) or "wazuh-manager")}
    elif integration_id == "salt":
        salt = config.get("salt", {})
        values = salt if isinstance(salt, dict) else {}
        service = {"api_url": service_url}
        bootstrap = {"master_url": str(values.get("master_url") or public_host(portal_url) or "salt-master")}
    elif integration_id in {"opensearch", "nats"}:
        service = {"url": service_url}
    return {"service": service, "bootstrap": bootstrap}


def clean_setup_values(values: object, allowed: set[str]) -> dict[str, str]:
    if not isinstance(values, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        if key not in allowed:
            raise ValidationError(f"unsupported integration setup field: {key}")
        cleaned[key] = str(value or "").strip()
    return cleaned


def configure_integration(context: TenantContext, integration_id: str, payload: dict[str, object]) -> dict[str, object]:
    if not context.platform_admin:
        raise AccessDenied("only platform admins can configure integrations")
    spec = INTEGRATION_SETUP_FIELDS.get(integration_id)
    if spec is None:
        raise NotFound(f"integration not found: {integration_id}")
    if payload.get("use_defaults") is True:
        defaults = integration_setup_defaults(integration_id, deployment_config())
        service = clean_setup_values(defaults.get("service", {}), spec["service"])
        bootstrap = clean_setup_values(defaults.get("bootstrap", {}), spec["bootstrap"])
    else:
        service = clean_setup_values(payload.get("service", {}), spec["service"])
        bootstrap = clean_setup_values(payload.get("bootstrap", {}), spec["bootstrap"])
    if integration_id == "meshcentral" and service.get("url") and not bootstrap.get("server_url"):
        bootstrap["server_url"] = service["url"]
    integration = save_runtime_integration(integration_id, service, bootstrap)
    if payload.get("run_setup") is True:
        integration = run_runtime_setup(integration_id)
    return {"integration": integration, "status": integration_status()}


def ensure_runtime_integrations(config: dict[str, object]) -> None:
    for integration_id in INTEGRATION_SETUP_FIELDS:
        runtime = _runtime_integration(integration_id)
        init = runtime.get("init", {}) if isinstance(runtime.get("init"), dict) else {}
        if _is_initialized(runtime):
            continue
        defaults = integration_setup_defaults(integration_id, config)
        save_runtime_integration(integration_id, defaults.get("service", {}), defaults.get("bootstrap", {}))
        if integration_id in {"identity", "opensearch", "nats"} or not init:
            continue
        run_runtime_setup(integration_id)


def integration_status() -> dict[str, object]:
    config = deployment_config()
    ensure_runtime_integrations(config)
    config = deployment_config()
    runtime_config = load_runtime_config()
    identity_missing = [
        name
        for name in ("KEYCLOAK_URL", "OIDC_CLIENT_ID")
        if not _identity_config_value(name)
    ]
    integrations = [
        _identity_integration(identity_missing),
        _agent_integration(
            "meshcentral",
            "MeshCentral",
            config["meshcentral"],  # type: ignore[index]
            required=("server_url",),
            bootstrap_required=("linux_installer_url",),
        ),
        _agent_integration(
            "zabbix",
            "Zabbix",
            config["zabbix"],  # type: ignore[index]
            required=("server_url",),
            bootstrap_required=(),
        ),
        _agent_integration(
            "wazuh",
            "Wazuh",
            config["wazuh"],  # type: ignore[index]
            required=("manager_url",),
            bootstrap_required=(),
        ),
        _agent_integration(
            "salt",
            "Salt",
            config["salt"],  # type: ignore[index]
            required=("master_url",),
            bootstrap_required=(),
        ),
        _runtime_only_integration("opensearch", "OpenSearch"),
        _runtime_only_integration("nats", "NATS JetStream"),
    ]
    configured_count = sum(1 for item in integrations if item["configured"])
    initialized_count = sum(1 for item in integrations if item["initialized"])
    return {
        "auth_mode": "header-simulated",
        "runtime_config_loaded": bool(runtime_config),
        "ready_for_real_endpoints": configured_count == len(integrations) and initialized_count == len(integrations),
        "configured_count": configured_count,
        "initialized_count": initialized_count,
        "total_count": len(integrations),
        "integrations": integrations,
    }


def _identity_integration(missing: list[str]) -> dict[str, object]:
    runtime = _runtime_integration("identity")
    initialized = _is_initialized(runtime)
    configured = not missing
    return {
        "id": "identity",
        "name": "Keycloak / SSO",
        "state": _integration_state(configured, initialized, "simulated"),
        "configured": configured,
        "initialized": initialized,
        "adapter_implemented": False,
        "service_url": _identity_config_value("KEYCLOAK_URL"),
        "service": runtime.get("service", {}) if isinstance(runtime.get("service"), dict) else {},
        "bootstrap": runtime.get("bootstrap", {}) if isinstance(runtime.get("bootstrap"), dict) else {},
        "summary": (
            "Keycloak service defaults are configured for the bundled stack."
            if configured
            else "Technician identity is currently simulated with X-FizRMM-* headers."
        ),
        "missing": missing,
        "setup_required": not initialized,
        "setup_steps": INTEGRATION_SETUP_STEPS["identity"] if not initialized else [],
        "setup_defaults": integration_setup_defaults("identity", deployment_config()),
        "setup_fields": {"service": sorted(INTEGRATION_SETUP_FIELDS["identity"]["service"]), "bootstrap": sorted(INTEGRATION_SETUP_FIELDS["identity"]["bootstrap"])},
        "init": runtime.get("init", {}) if isinstance(runtime.get("init"), dict) else {},
    }


def _agent_integration(
    integration_id: str,
    name: str,
    config: object,
    required: tuple[str, ...],
    bootstrap_required: tuple[str, ...] = (),
) -> dict[str, object]:
    values = config if isinstance(config, dict) else {}
    missing = [field for field in required if not str(values.get(field) or "").strip()]
    bootstrap_missing = _bootstrap_missing(values, bootstrap_required)
    runtime = _runtime_integration(integration_id)
    configured = not missing
    initialized = _is_initialized(runtime)
    return {
        "id": integration_id,
        "name": name,
        "state": _integration_state(configured, initialized),
        "configured": configured,
        "initialized": initialized,
        "adapter_implemented": False,
        "service_url": _service_url(integration_id) or _first_config_value(values, required),
        "service": runtime.get("service", {}) if isinstance(runtime.get("service"), dict) else {},
        "bootstrap": values,
        "summary": (
            f"{name} service defaults are configured for the bundled stack."
            if configured
            else f"{name} service settings are incomplete."
        ),
        "missing": missing,
        "bootstrap_missing": bootstrap_missing,
        "setup_required": bool(missing or bootstrap_missing or not initialized),
        "setup_steps": INTEGRATION_SETUP_STEPS.get(integration_id, []) if (missing or bootstrap_missing or not initialized) else [],
        "setup_defaults": integration_setup_defaults(integration_id, deployment_config()),
        "setup_fields": {"service": sorted(INTEGRATION_SETUP_FIELDS[integration_id]["service"]), "bootstrap": sorted(INTEGRATION_SETUP_FIELDS[integration_id]["bootstrap"])},
        "init": runtime.get("init", {}) if isinstance(runtime.get("init"), dict) else {},
    }


def _bootstrap_missing(values: dict[str, object], required: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for field in required:
        if " or " in field:
            options = tuple(part.strip() for part in field.split(" or "))
            if not any(str(values.get(option) or "").strip() for option in options):
                missing.append(field)
        elif not str(values.get(field) or "").strip():
            missing.append(field)
    return missing


def _first_config_value(values: dict[str, object], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(values.get(field) or "").strip()
        if value:
            return value
    return ""


def _runtime_only_integration(integration_id: str, name: str) -> dict[str, object]:
    runtime = _runtime_integration(integration_id)
    service_url = _service_url(integration_id)
    configured = bool(service_url)
    initialized = _is_initialized(runtime)
    return {
        "id": integration_id,
        "name": name,
        "state": _integration_state(configured, initialized),
        "configured": configured,
        "initialized": initialized,
        "adapter_implemented": False,
        "service_url": service_url,
        "service": runtime.get("service", {}) if isinstance(runtime.get("service"), dict) else {},
        "bootstrap": runtime.get("bootstrap", {}) if isinstance(runtime.get("bootstrap"), dict) else {},
        "summary": f"{name} service defaults are {'configured' if configured else 'missing'}.",
        "missing": [] if configured else ["service.url"],
        "setup_required": not initialized,
        "setup_steps": INTEGRATION_SETUP_STEPS.get(integration_id, []) if not initialized else [],
        "setup_defaults": integration_setup_defaults(integration_id, deployment_config()),
        "setup_fields": {"service": sorted(INTEGRATION_SETUP_FIELDS[integration_id]["service"]), "bootstrap": sorted(INTEGRATION_SETUP_FIELDS[integration_id]["bootstrap"])},
        "init": runtime.get("init", {}) if isinstance(runtime.get("init"), dict) else {},
    }


def _runtime_integration(integration_id: str) -> dict[str, object]:
    integrations = load_runtime_config().get("integrations", {})
    value = integrations.get(integration_id) if isinstance(integrations, dict) else None
    return value if isinstance(value, dict) else {}


def _runtime_identity_value(env_name: str) -> str:
    key_map = {
        "KEYCLOAK_URL": ("url",),
        "OIDC_CLIENT_ID": ("client_id",),
        "OIDC_CLIENT_SECRET": ("client_secret",),
    }
    keys = key_map.get(env_name, ())
    for key in keys:
        value = runtime_service_value("identity", key, "")
        if value:
            return value
    return ""


def _identity_config_value(env_name: str) -> str:
    defaults = {
        "KEYCLOAK_URL": BUNDLED_SERVICE_URLS["identity"],
        "OIDC_CLIENT_ID": "fizrmm-portal",
        "OIDC_CLIENT_SECRET": env_value("OIDC_CLIENT_SECRET"),
    }
    return os.getenv(env_name, "").strip() or _runtime_identity_value(env_name) or defaults.get(env_name, "")


def _service_url(integration_id: str) -> str:
    for key in ("url", "api_url"):
        value = runtime_service_value(integration_id, key, "")
        if value:
            return value
    env_map = {
        "identity": "KEYCLOAK_URL",
        "meshcentral": "MESHCENTRAL_URL",
        "zabbix": "ZABBIX_API_URL",
        "wazuh": "WAZUH_API_URL",
        "salt": "SALT_API_URL",
        "opensearch": "OPENSEARCH_URL",
        "nats": "NATS_URL",
    }
    env_name = env_map.get(integration_id, "")
    if env_name and os.getenv(env_name, "").strip():
        return os.getenv(env_name, "").strip()
    return BUNDLED_SERVICE_URLS.get(integration_id, "")


def _is_initialized(runtime: dict[str, object]) -> bool:
    init = runtime.get("init")
    if not isinstance(init, dict):
        return False
    status = str(init.get("status") or "").strip().lower()
    return status in {"configured", "initialized", "ready"}


def _integration_state(configured: bool, initialized: bool, fallback: str = "missing_config") -> str:
    if configured and initialized:
        return "initialized"
    if configured:
        return "configured"
    if initialized:
        return "init_incomplete"
    return fallback


def context_from_headers(headers: Any) -> TenantContext:
    token_context = context_from_authorization(headers.get("Authorization"))
    if token_context is not None:
        return token_context
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
        except (KeyError, TypeError) as exc:
            self._send_json({"error": f"invalid request: {exc}"}, status=HTTPStatus.BAD_REQUEST)
        except Exception:
            self._send_json({"error": "internal server error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

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
        if parts == ["api", "integrations"]:
            return integration_status()
        if len(parts) == 4 and parts[:2] == ["api", "enrollments"] and parts[3] == "bootstrap.ps1":
            enrollment = STORE.get_enrollment_by_token(parts[2])
            portal_url = public_portal_url(self.headers, enrollment.config.get("portal_url"))
            return TextResponse(render_windows_bootstrap(portal_url, parts[2]), "text/plain; charset=utf-8")
        if len(parts) == 4 and parts[:2] == ["api", "enrollments"] and parts[3] == "bootstrap.sh":
            enrollment = STORE.get_enrollment_by_token(parts[2])
            portal_url = public_portal_url(self.headers, enrollment.config.get("portal_url"))
            return TextResponse(render_linux_bootstrap(portal_url, parts[2]), "text/x-shellscript; charset=utf-8")
        raise NotFound("route not found")

    def _route_post(self, context: TenantContext, parts: list[str]) -> Any:
        if parts == ["api", "orgs"]:
            payload = self._read_payload()
            return {
                "organization": STORE.create_organization(
                    context=context,
                    name=str(payload.get("name") or ""),
                    org_id=str(payload.get("id") or "").strip() or None,
                )
            }
        if len(parts) == 4 and parts[:2] == ["api", "integrations"] and parts[3] == "setup":
            payload = self._read_payload()
            return configure_integration(context, parts[2], payload)
        if parts == ["api", "enrollments"]:
            payload = self._read_payload()
            expires_hours = int(payload.get("expires_hours", 24))
            if expires_hours < 1 or expires_hours > 168:
                raise ValidationError("expires_hours must be between 1 and 168")
            expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)
            config = deployment_config()
            config["portal_url"] = public_portal_url(self.headers, config.get("portal_url"))
            apply_meshcentral_agent_defaults(config, str(config["portal_url"]))
            return STORE.create_enrollment(
                context=context,
                org_id=payload.get("org_id", context.allowed_org_ids[0] if context.allowed_org_ids else ""),
                site=payload.get("site", "Default"),
                config=config,
                expires_at=expires_at.isoformat(),
            )
        if len(parts) == 4 and parts[:2] == ["api", "enrollments"] and parts[3] == "claim":
            payload = self._read_payload()
            enrollment = STORE.get_enrollment_by_token(parts[2])
            config = dict(enrollment.config)
            meshcentral = config.get("meshcentral")
            if isinstance(meshcentral, dict):
                config["meshcentral"] = dict(meshcentral)
            portal_url = public_portal_url(self.headers, config.get("portal_url"))
            config["portal_url"] = portal_url
            apply_meshcentral_agent_defaults(config, portal_url)
            require_meshcentral_agent_config(config)
            claim = STORE.claim_enrollment(
                token=parts[2],
                hostname=payload.get("hostname", "unknown"),
                operating_system=payload.get("operating_system", "unknown"),
            )
            claim["config"] = config
            return claim
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
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValidationError("request body must be a JSON object")
        return payload

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
