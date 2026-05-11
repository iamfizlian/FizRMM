from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
import re
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4

from .models import (
    AccessDenied,
    AgentHealth,
    AgentKind,
    Asset,
    AssetState,
    AuditEvent,
    ConnectorIdentity,
    EndpointEnrollment,
    NotFound,
    Organization,
    ScriptDefinition,
    TenantContext,
    TimelineEvent,
    TimelineKind,
    ValidationError,
    parse_iso_datetime,
    utcnow_iso,
)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class PostgresControlPlaneStore:
    name = "postgres"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def _cursor(self, context: TenantContext | None = None) -> Iterator[Any]:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                if context is not None:
                    cur.execute(
                        "select set_config('app.platform_admin', %s, true)",
                        ("true" if context.platform_admin else "false",),
                    )
                    cur.execute(
                        "select set_config('app.org_ids', %s, true)",
                        (",".join(context.allowed_org_ids),),
                    )
                yield cur

    def health(self) -> dict[str, str]:
        with self._cursor() as cur:
            cur.execute("select 1 as ok")
            cur.fetchone()
        return {"store": self.name, "status": "ok"}

    def list_organizations(self, context: TenantContext) -> list[Organization]:
        with self._cursor(context) as cur:
            cur.execute("select id, name, status from organizations order by name")
            return [self._organization(row) for row in cur.fetchall()]

    def create_organization(self, context: TenantContext, name: str, org_id: str | None = None) -> Organization:
        if not context.platform_admin:
            raise AccessDenied("only platform admins can create organizations")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValidationError("organization name is required")
        normalized_id = org_id.strip() if org_id else f"org_{re.sub(r'[^a-z0-9]+', '_', normalized_name.lower()).strip('_')}"
        if not normalized_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", normalized_id):
            raise ValidationError("organization id may only contain letters, numbers, underscores, and hyphens")
        with self._cursor(context) as cur:
            cur.execute(
                """
                insert into organizations (id, name)
                values (%s, %s)
                on conflict (id) do nothing
                returning id, name, status
                """,
                (normalized_id, normalized_name),
            )
            row = cur.fetchone()
        if row is None:
            raise ValidationError(f"organization already exists: {normalized_id}")
        return self._organization(row)

    def list_assets(self, context: TenantContext) -> list[Asset]:
        with self._cursor(context) as cur:
            cur.execute(
                """
                select id, org_id, hostname, operating_system, site, state
                from assets
                order by hostname
                """
            )
            return [self._asset(row) for row in cur.fetchall()]

    def get_asset(self, context: TenantContext, asset_id: str) -> Asset:
        self._require_asset_access(context, asset_id)
        with self._cursor(context) as cur:
            cur.execute(
                """
                select id, org_id, hostname, operating_system, site, state
                from assets
                where id = %s
                """,
                (asset_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise NotFound(f"asset not found: {asset_id}")
            return self._asset(row)

    def list_connectors(self, context: TenantContext, asset_id: str) -> list[ConnectorIdentity]:
        self._require_asset_access(context, asset_id)
        with self._cursor(context) as cur:
            cur.execute(
                """
                select asset_id, org_id, connector, external_id, metadata
                from connector_identities
                where asset_id = %s
                order by connector
                """,
                (asset_id,),
            )
            return [self._connector(row) for row in cur.fetchall()]

    def list_agent_health(self, context: TenantContext, asset_id: str) -> list[AgentHealth]:
        self._require_asset_access(context, asset_id)
        with self._cursor(context) as cur:
            cur.execute(
                """
                select asset_id, org_id, agent, version, service_state, last_seen_at, update_channel, resource_status
                from agent_health
                where asset_id = %s
                order by agent
                """,
                (asset_id,),
            )
            return [self._agent_health(row) for row in cur.fetchall()]

    def list_timeline(self, context: TenantContext, asset_id: str) -> list[TimelineEvent]:
        self._require_asset_access(context, asset_id)
        with self._cursor(context) as cur:
            cur.execute(
                """
                select id, org_id, asset_id, kind, title, body, source, details, created_at
                from timeline_events
                where asset_id = %s
                order by created_at desc
                """,
                (asset_id,),
            )
            return [self._timeline_event(row) for row in cur.fetchall()]

    def list_scripts(self, context: TenantContext) -> list[ScriptDefinition]:
        with self._cursor(context) as cur:
            cur.execute(
                """
                select id, org_id, name, runtime, revision, approval_required
                from script_definitions
                order by name
                """
            )
            return [self._script(row) for row in cur.fetchall()]

    def create_remote_session(
        self,
        context: TenantContext,
        asset_id: str,
        engine: str,
    ) -> dict[str, str]:
        from psycopg.types.json import Jsonb

        if engine not in {"meshcentral", "guacamole"}:
            raise ValueError("engine must be meshcentral or guacamole")
        asset = self.get_asset(context, asset_id)
        session_id = f"remote-{uuid4()}"
        event_id = str(uuid4())
        audit_id = str(uuid4())

        with self._cursor(context) as cur:
            cur.execute(
                """
                insert into audit_events (id, org_id, actor_user_id, action, asset_id, result, details)
                values (%s, %s, %s, 'remote_session.launch_requested', %s, 'accepted', %s)
                """,
                (
                    audit_id,
                    asset.org_id,
                    context.user_id,
                    asset.id,
                    Jsonb({"engine": engine, "session_id": session_id}),
                ),
            )
            cur.execute(
                """
                insert into timeline_events (id, org_id, asset_id, kind, title, body, source, details)
                values (%s, %s, %s, 'remote_session', %s, %s, 'portal', %s)
                """,
                (
                    event_id,
                    asset.org_id,
                    asset.id,
                    f"{engine.title()} session requested",
                    f"{context.user_id} requested a portal-brokered remote session.",
                    Jsonb({"engine": engine, "session_id": session_id}),
                ),
            )

        return {
            "session_id": session_id,
            "engine": engine,
            "launch_url": f"https://portal.local/remote/{engine}/{session_id}",
        }

    def create_script_run(
        self,
        context: TenantContext,
        asset_id: str,
        script_id: str,
    ) -> dict[str, str]:
        from psycopg.types.json import Jsonb

        asset = self.get_asset(context, asset_id)
        script = self._get_script(context, script_id)
        job_id = f"salt-job-{uuid4()}"

        with self._cursor(context) as cur:
            cur.execute(
                """
                insert into audit_events (id, org_id, actor_user_id, action, asset_id, result, details)
                values (%s, %s, %s, 'script_run.requested', %s, 'accepted', %s)
                """,
                (
                    str(uuid4()),
                    asset.org_id,
                    context.user_id,
                    asset.id,
                    Jsonb({"script_id": script.id, "job_id": job_id}),
                ),
            )
            cur.execute(
                """
                insert into timeline_events (id, org_id, asset_id, kind, title, body, source, details)
                values (%s, %s, %s, 'script_run', %s, %s, 'portal', %s)
                """,
                (
                    str(uuid4()),
                    asset.org_id,
                    asset.id,
                    f"Script queued: {script.name}",
                    "Portal accepted the script run and queued it for Salt execution.",
                    Jsonb({"script_id": script.id, "job_id": job_id}),
                ),
            )

        return {"job_id": job_id, "status": "queued", "executor": "salt"}

    def create_enrollment(
        self,
        context: TenantContext,
        org_id: str,
        site: str,
        config: dict[str, object],
        expires_at: str,
    ) -> dict[str, object]:
        from psycopg.types.json import Jsonb

        if not context.can_access_org(org_id):
            raise AccessDenied(f"user cannot access org: {org_id}")
        token = token_urlsafe(32)
        enrollment_id = str(uuid4())
        with self._cursor(context) as cur:
            cur.execute(
                """
                insert into endpoint_enrollments (id, org_id, site, token, status, created_by, config, expires_at)
                values (%s, %s, %s, %s, 'active', %s, %s, %s)
                returning id, org_id, site, token, status, created_by, asset_id, expires_at, claimed_at, completed_at, config
                """,
                (
                    enrollment_id,
                    org_id,
                    site,
                    token,
                    context.user_id,
                    Jsonb(config),
                    expires_at,
                ),
            )
            enrollment = self._enrollment(cur.fetchone())

        return {
            "enrollment": enrollment,
            "token": token,
            "bootstrap_url": f"/api/enrollments/{token}/bootstrap.ps1",
            "linux_bootstrap_url": f"/api/enrollments/{token}/bootstrap.sh",
            "command": (
                "powershell.exe -ExecutionPolicy Bypass -File .\\fizrmm-bootstrap.ps1 "
                f"-PortalUrl {config.get('portal_url')} -EnrollmentToken {token}"
            ),
            "linux_command": (
                f"curl -fsSL {config.get('portal_url')}/api/enrollments/{token}/bootstrap.sh "
                "-o fizrmm-bootstrap.sh && sudo bash ./fizrmm-bootstrap.sh"
            ),
        }

    def get_enrollment_by_token(self, token: str) -> EndpointEnrollment:
        with self._system_cursor() as cur:
            cur.execute(
                """
                select id, org_id, site, token, status, created_by, asset_id, expires_at, claimed_at, completed_at, config
                from endpoint_enrollments
                where token = %s
                """,
                (token,),
            )
            row = cur.fetchone()
        if row is None:
            raise NotFound("enrollment token not found")
        return self._enrollment(row)

    def _active_enrollment(self, token: str) -> EndpointEnrollment:
        enrollment = self.get_enrollment_by_token(token)
        if enrollment.status != "active":
            raise ValidationError(f"enrollment token is {enrollment.status}")
        if parse_iso_datetime(enrollment.expires_at) <= parse_iso_datetime(utcnow_iso()):
            raise ValidationError("enrollment token has expired")
        return enrollment

    def claim_enrollment(
        self,
        token: str,
        hostname: str,
        operating_system: str,
    ) -> dict[str, object]:
        from psycopg.types.json import Jsonb

        if not hostname.strip():
            raise ValidationError("hostname is required")
        if not operating_system.strip():
            raise ValidationError("operating_system is required")

        enrollment = self.get_enrollment_by_token(token)
        if parse_iso_datetime(enrollment.expires_at) <= parse_iso_datetime(utcnow_iso()):
            raise ValidationError("enrollment token has expired")
        if enrollment.status in {"claimed", "completed"} and enrollment.asset_id:
            return {
                "asset_id": enrollment.asset_id,
                "org_id": enrollment.org_id,
                "site": enrollment.site,
                "config": enrollment.config,
            }
        if enrollment.status != "active":
            raise ValidationError(f"enrollment token is {enrollment.status}")
        asset_id = enrollment.asset_id or f"asset-{uuid4()}"
        with self._system_cursor() as cur:
            cur.execute(
                """
                insert into assets (id, org_id, hostname, operating_system, site, state)
                values (%s, %s, %s, %s, %s, 'active')
                on conflict (id) do update
                    set hostname = excluded.hostname,
                        operating_system = excluded.operating_system,
                        site = excluded.site,
                        updated_at = now()
                """,
                (asset_id, enrollment.org_id, hostname, operating_system, enrollment.site),
            )
            cur.execute(
                """
                update endpoint_enrollments
                set asset_id = %s,
                    status = 'claimed',
                    claimed_at = coalesce(claimed_at, now())
                where token = %s
                """,
                (asset_id, token),
            )
            cur.execute(
                """
                insert into timeline_events (id, org_id, asset_id, kind, title, body, source, details)
                values (%s, %s, %s, 'enrollment', 'Endpoint enrollment claimed', %s, 'bootstrap', %s)
                """,
                (
                    str(uuid4()),
                    enrollment.org_id,
                    asset_id,
                    f"{hostname} claimed an endpoint enrollment token.",
                    Jsonb({"site": enrollment.site}),
                ),
            )

        return {
            "asset_id": asset_id,
            "org_id": enrollment.org_id,
            "site": enrollment.site,
            "config": enrollment.config,
        }

    def report_enrollment(
        self,
        token: str,
        agents: list[dict[str, object]],
    ) -> dict[str, object]:
        from psycopg.types.json import Jsonb

        enrollment = self.get_enrollment_by_token(token)
        if not isinstance(agents, list):
            raise ValidationError("agents must be a list")
        if parse_iso_datetime(enrollment.expires_at) <= parse_iso_datetime(utcnow_iso()):
            raise ValidationError("enrollment token has expired")
        if enrollment.status == "completed":
            return {"asset_id": enrollment.asset_id, "status": enrollment.status, "agents_reported": len(agents)}
        if enrollment.status != "claimed":
            raise ValidationError(f"enrollment token is {enrollment.status}")
        if enrollment.asset_id is None:
            raise ValueError("enrollment must be claimed before reporting")

        with self._system_cursor() as cur:
            for agent_report in agents:
                if not isinstance(agent_report, dict):
                    raise ValidationError("agent report entries must be objects")
                agent = str(agent_report.get("agent") or "")
                try:
                    AgentKind(agent)
                except ValueError as exc:
                    raise ValidationError(f"unsupported agent: {agent}") from exc
                external_id = str(agent_report.get("external_id") or f"{agent}:{enrollment.asset_id}")
                cur.execute(
                    """
                    insert into connector_identities (org_id, asset_id, connector, external_id, metadata)
                    values (%s, %s, %s, %s, %s)
                    on conflict (connector, external_id) do update
                        set metadata = excluded.metadata
                    """,
                    (
                        enrollment.org_id,
                        enrollment.asset_id,
                        agent,
                        external_id,
                        Jsonb({"source": "bootstrap"}),
                    ),
                )
                cur.execute(
                    """
                    insert into agent_health (
                        org_id, asset_id, agent, version, service_state, last_seen_at, update_channel, resource_status
                    )
                    values (%s, %s, %s, %s, %s, now(), %s, %s)
                    on conflict (asset_id, agent) do update
                        set version = excluded.version,
                            service_state = excluded.service_state,
                            last_seen_at = excluded.last_seen_at,
                            update_channel = excluded.update_channel,
                            resource_status = excluded.resource_status,
                            updated_at = now()
                    """,
                    (
                        enrollment.org_id,
                        enrollment.asset_id,
                        agent,
                        str(agent_report.get("version") or "unknown"),
                        str(agent_report.get("status") or "reported"),
                        str(agent_report.get("update_channel") or "bootstrap"),
                        str(agent_report.get("resource_status") or "unknown"),
                    ),
                )
            cur.execute(
                """
                update endpoint_enrollments
                set status = 'completed',
                    completed_at = coalesce(completed_at, now())
                where token = %s
                """,
                (token,),
            )
            cur.execute(
                """
                insert into timeline_events (id, org_id, asset_id, kind, title, body, source, details)
                values (%s, %s, %s, 'agent_health', 'Endpoint bootstrap reported', %s, 'bootstrap', %s)
                """,
                (
                    str(uuid4()),
                    enrollment.org_id,
                    enrollment.asset_id,
                    f"Bootstrap reported {len(agents)} agent states.",
                    Jsonb({"agents": agents}),
                ),
            )

        return {"asset_id": enrollment.asset_id, "status": "completed", "agents_reported": len(agents)}

    def _require_asset_access(self, context: TenantContext, asset_id: str) -> None:
        with self._system_cursor() as cur:
            cur.execute("select org_id from assets where id = %s", (asset_id,))
            row = cur.fetchone()
        org_id = row["org_id"] if row else None
        if org_id is None:
            raise NotFound(f"asset not found: {asset_id}")
        if not context.can_access_org(org_id):
            raise AccessDenied(f"user cannot access org: {org_id}")

    @contextmanager
    def _system_cursor(self) -> Iterator[Any]:
        system_context = TenantContext(
            user_id="system",
            allowed_org_ids=(),
            role="platform-admin",
            platform_admin=True,
        )
        with self._cursor(system_context) as cur:
            yield cur

    def _get_script(self, context: TenantContext, script_id: str) -> ScriptDefinition:
        with self._system_cursor() as cur:
            cur.execute("select org_id from script_definitions where id = %s", (script_id,))
            row = cur.fetchone()
        if row is None:
            raise NotFound(f"script not found: {script_id}")
        org_id = row["org_id"]
        if org_id is not None and not context.can_access_org(org_id):
            raise AccessDenied(f"user cannot access org: {org_id}")

        with self._cursor(context) as cur:
            cur.execute(
                """
                select id, org_id, name, runtime, revision, approval_required
                from script_definitions
                where id = %s
                """,
                (script_id,),
            )
            script_row = cur.fetchone()
        if script_row is None:
            raise NotFound(f"script not found: {script_id}")
        return self._script(script_row)

    def _organization(self, row: dict[str, Any]) -> Organization:
        return Organization(id=row["id"], name=row["name"], status=row["status"])

    def _asset(self, row: dict[str, Any]) -> Asset:
        return Asset(
            id=row["id"],
            org_id=row["org_id"],
            hostname=row["hostname"],
            operating_system=row["operating_system"],
            site=row["site"] or "",
            state=AssetState(row["state"]),
        )

    def _connector(self, row: dict[str, Any]) -> ConnectorIdentity:
        return ConnectorIdentity(
            asset_id=row["asset_id"],
            org_id=row["org_id"],
            connector=AgentKind(row["connector"]),
            external_id=row["external_id"],
            metadata=row["metadata"] or {},
        )

    def _agent_health(self, row: dict[str, Any]) -> AgentHealth:
        return AgentHealth(
            asset_id=row["asset_id"],
            org_id=row["org_id"],
            agent=AgentKind(row["agent"]),
            version=row["version"],
            service_state=row["service_state"],
            last_seen_at=_iso(row["last_seen_at"]),
            update_channel=row["update_channel"],
            resource_status=row["resource_status"],
        )

    def _script(self, row: dict[str, Any]) -> ScriptDefinition:
        return ScriptDefinition(
            id=row["id"],
            org_id=row["org_id"],
            name=row["name"],
            runtime=row["runtime"],
            revision=row["revision"],
            approval_required=row["approval_required"],
        )

    def _timeline_event(self, row: dict[str, Any]) -> TimelineEvent:
        return TimelineEvent(
            id=str(row["id"]),
            org_id=row["org_id"],
            asset_id=row["asset_id"],
            kind=TimelineKind(row["kind"]),
            title=row["title"],
            body=row["body"],
            source=row["source"],
            details=row["details"] or {},
            created_at=_iso(row["created_at"]),
        )

    def _enrollment(self, row: dict[str, Any]) -> EndpointEnrollment:
        return EndpointEnrollment(
            id=str(row["id"]),
            org_id=row["org_id"],
            site=row["site"],
            token=row["token"],
            status=row["status"],
            created_by=row["created_by"],
            asset_id=row["asset_id"],
            expires_at=_iso(row["expires_at"]),
            claimed_at=_iso(row["claimed_at"]) if row["claimed_at"] is not None else None,
            completed_at=_iso(row["completed_at"]) if row["completed_at"] is not None else None,
            config=row["config"] or {},
        )
