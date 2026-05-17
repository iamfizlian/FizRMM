from __future__ import annotations

from uuid import uuid4
from urllib.parse import urlencode
import os
import re
from secrets import token_urlsafe

from .enrollment_commands import enrollment_bootstrap_payload
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


class InMemoryControlPlaneStore:
    name = "in-memory"

    def __init__(self) -> None:
        self.organizations: dict[str, Organization] = {}
        self.assets: dict[str, Asset] = {}
        self.connectors: list[ConnectorIdentity] = []
        self.agent_health: list[AgentHealth] = []
        self.scripts: dict[str, ScriptDefinition] = {}
        self.audit_events: list[AuditEvent] = []
        self.timeline_events: list[TimelineEvent] = []
        self.enrollments: dict[str, EndpointEnrollment] = {}

    def health(self) -> dict[str, str]:
        return {"store": self.name, "status": "ok"}

    def list_organizations(self, context: TenantContext) -> list[Organization]:
        return [
            org
            for org in self.organizations.values()
            if context.can_access_org(org.id)
        ]

    def create_organization(self, context: TenantContext, name: str, org_id: str | None = None) -> Organization:
        if not context.platform_admin:
            raise AccessDenied("only platform admins can create organizations")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValidationError("organization name is required")
        normalized_id = org_id.strip() if org_id else f"org_{re.sub(r'[^a-z0-9]+', '_', normalized_name.lower()).strip('_')}"
        if not normalized_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", normalized_id):
            raise ValidationError("organization id may only contain letters, numbers, underscores, and hyphens")
        if normalized_id in self.organizations:
            raise ValidationError(f"organization already exists: {normalized_id}")
        organization = Organization(id=normalized_id, name=normalized_name)
        self.organizations[normalized_id] = organization
        return organization

    def list_assets(self, context: TenantContext) -> list[Asset]:
        return [
            asset
            for asset in self.assets.values()
            if context.can_access_org(asset.org_id)
        ]

    def get_asset(self, context: TenantContext, asset_id: str) -> Asset:
        asset = self.assets.get(asset_id)
        if asset is None:
            raise NotFound(f"asset not found: {asset_id}")
        self._require_org(context, asset.org_id)
        return asset

    def delete_asset(self, context: TenantContext, asset_id: str) -> dict[str, str]:
        asset = self.get_asset(context, asset_id)
        del self.assets[asset.id]
        self.connectors = [connector for connector in self.connectors if connector.asset_id != asset.id]
        self.agent_health = [health for health in self.agent_health if health.asset_id != asset.id]
        self.timeline_events = [event for event in self.timeline_events if event.asset_id != asset.id]
        self.audit_events = [
            AuditEvent(
                **{
                    **event.__dict__,
                    "asset_id": None,
                    "details": {**event.details, "deleted_asset_id": asset.id},
                }
            )
            if event.asset_id == asset.id
            else event
            for event in self.audit_events
        ]
        self.enrollments = {
            token: (
                EndpointEnrollment(**{**enrollment.__dict__, "asset_id": None})
                if enrollment.asset_id == asset.id
                else enrollment
            )
            for token, enrollment in self.enrollments.items()
        }
        return {"asset_id": asset.id, "status": "deleted"}

    def list_connectors(self, context: TenantContext, asset_id: str) -> list[ConnectorIdentity]:
        asset = self.get_asset(context, asset_id)
        return [
            connector
            for connector in self.connectors
            if connector.asset_id == asset.id and context.can_access_org(connector.org_id)
        ]

    def list_agent_health(self, context: TenantContext, asset_id: str) -> list[AgentHealth]:
        asset = self.get_asset(context, asset_id)
        return [
            health
            for health in self.agent_health
            if health.asset_id == asset.id and context.can_access_org(health.org_id)
        ]

    def list_timeline(self, context: TenantContext, asset_id: str) -> list[TimelineEvent]:
        asset = self.get_asset(context, asset_id)
        events = [
            event
            for event in self.timeline_events
            if event.asset_id == asset.id and context.can_access_org(event.org_id)
        ]
        return sorted(events, key=lambda event: event.created_at, reverse=True)

    def list_scripts(self, context: TenantContext) -> list[ScriptDefinition]:
        return [
            script
            for script in self.scripts.values()
            if script.org_id is None or context.can_access_org(script.org_id)
        ]

    def create_remote_session(
        self,
        context: TenantContext,
        asset_id: str,
        engine: str,
    ) -> dict[str, str]:
        asset = self.get_asset(context, asset_id)
        if engine not in {"meshcentral", "guacamole"}:
            raise ValueError("engine must be meshcentral or guacamole")

        session_id = f"remote-{uuid4()}"
        now = utcnow_iso()
        self.audit_events.append(
            AuditEvent(
                id=str(uuid4()),
                org_id=asset.org_id,
                actor_user_id=context.user_id,
                action="remote_session.launch_requested",
                asset_id=asset.id,
                result="accepted",
                details={"engine": engine, "session_id": session_id},
                created_at=now,
            )
        )
        self.timeline_events.append(
            TimelineEvent(
                id=str(uuid4()),
                org_id=asset.org_id,
                asset_id=asset.id,
                kind=TimelineKind.REMOTE_SESSION,
                title=f"{engine.title()} session requested",
                body=f"{context.user_id} requested a portal-brokered remote session.",
                source="portal",
                details={"engine": engine, "session_id": session_id},
                created_at=now,
            )
        )
        agent_state = next(
            (
                health.service_state
                for health in self.agent_health
                if health.asset_id == asset.id and health.agent == AgentKind.MESHCENTRAL
            ),
            "unknown",
        )
        status = "brokered"
        message = "Remote session request recorded."
        if engine == "meshcentral" and agent_state.startswith("skipped"):
            status = "agent_not_installed"
            message = "MeshCentral is not installed on this endpoint. Configure a Linux MeshCentral installer URL and re-run enrollment."
        elif engine == "meshcentral" and not os.getenv("MESHCENTRAL_URL", "").strip():
            status = "integration_not_configured"
            message = "MeshCentral server URL is not configured, so FizRMM can only record the request."
        elif engine == "guacamole" and not os.getenv("GUACAMOLE_URL", "").strip():
            status = "integration_not_configured"
            message = "Guacamole broker URL is not configured, so FizRMM can only record the request."
        query = urlencode({"status": status, "message": message, "asset": asset.hostname})
        return {
            "session_id": session_id,
            "engine": engine,
            "status": status,
            "message": message,
            "launch_url": f"/remote/{engine}/{session_id}?{query}",
        }

    def create_script_run(
        self,
        context: TenantContext,
        asset_id: str,
        script_id: str,
    ) -> dict[str, str]:
        asset = self.get_asset(context, asset_id)
        script = self.scripts.get(script_id)
        if script is None:
            raise NotFound(f"script not found: {script_id}")
        if script.org_id is not None:
            self._require_org(context, script.org_id)

        job_id = f"salt-job-{uuid4()}"
        now = utcnow_iso()
        self.audit_events.append(
            AuditEvent(
                id=str(uuid4()),
                org_id=asset.org_id,
                actor_user_id=context.user_id,
                action="script_run.requested",
                asset_id=asset.id,
                result="accepted",
                details={"script_id": script.id, "job_id": job_id},
                created_at=now,
            )
        )
        self.timeline_events.append(
            TimelineEvent(
                id=str(uuid4()),
                org_id=asset.org_id,
                asset_id=asset.id,
                kind=TimelineKind.SCRIPT_RUN,
                title=f"Script queued: {script.name}",
                body="Portal accepted the script run and queued it for Salt execution.",
                source="portal",
                details={"script_id": script.id, "job_id": job_id},
                created_at=now,
            )
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
        self._require_org(context, org_id)
        token = token_urlsafe(32)
        enrollment = EndpointEnrollment(
            id=str(uuid4()),
            org_id=org_id,
            site=site,
            token=token,
            status="active",
            created_by=context.user_id,
            asset_id=None,
            expires_at=expires_at,
            claimed_at=None,
            completed_at=None,
            config=config,
        )
        self.enrollments[token] = enrollment
        return enrollment_bootstrap_payload(enrollment, token, config)

    def get_enrollment_by_token(self, token: str) -> EndpointEnrollment:
        enrollment = self.enrollments.get(token)
        if enrollment is None:
            raise NotFound("enrollment token not found")
        return enrollment

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
        if asset_id not in self.assets:
            self.assets[asset_id] = Asset(
                id=asset_id,
                org_id=enrollment.org_id,
                hostname=hostname,
                operating_system=operating_system,
                site=enrollment.site,
                state=AssetState.ACTIVE,
            )
        claimed = EndpointEnrollment(
            **{
                **enrollment.__dict__,
                "asset_id": asset_id,
                "status": "claimed",
                "claimed_at": utcnow_iso(),
            }
        )
        self.enrollments[token] = claimed
        self.timeline_events.append(
            TimelineEvent(
                id=str(uuid4()),
                org_id=claimed.org_id,
                asset_id=asset_id,
                kind=TimelineKind.ENROLLMENT,
                title="Endpoint enrollment claimed",
                body=f"{hostname} claimed an endpoint enrollment token.",
                source="bootstrap",
                details={"site": claimed.site},
                created_at=utcnow_iso(),
            )
        )
        return {
            "asset_id": asset_id,
            "org_id": claimed.org_id,
            "site": claimed.site,
            "config": claimed.config,
        }

    def report_enrollment(
        self,
        token: str,
        agents: list[dict[str, object]],
    ) -> dict[str, object]:
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
        for agent_report in agents:
            if not isinstance(agent_report, dict):
                raise ValidationError("agent report entries must be objects")
            agent_name = str(agent_report.get("agent") or "")
            try:
                agent = AgentKind(agent_name)
            except ValueError as exc:
                raise ValidationError(f"unsupported agent: {agent_name}") from exc
            external_id = str(agent_report.get("external_id") or f"{agent.value}:{enrollment.asset_id}")
            existing_connector = next(
                (
                    connector
                    for connector in self.connectors
                    if connector.connector == agent and connector.external_id == external_id
                ),
                None,
            )
            if existing_connector is None:
                self.connectors.append(
                    ConnectorIdentity(
                        asset_id=enrollment.asset_id,
                        org_id=enrollment.org_id,
                        connector=agent,
                        external_id=external_id,
                        metadata={"source": "bootstrap"},
                    )
                )
            self.agent_health = [
                health
                for health in self.agent_health
                if not (health.asset_id == enrollment.asset_id and health.agent == agent)
            ]
            self.agent_health.append(
                AgentHealth(
                    asset_id=enrollment.asset_id,
                    org_id=enrollment.org_id,
                    agent=agent,
                    version=str(agent_report.get("version") or "unknown"),
                    service_state=str(agent_report.get("status") or "reported"),
                    last_seen_at=utcnow_iso(),
                    update_channel=str(agent_report.get("update_channel") or "bootstrap"),
                    resource_status=str(agent_report.get("resource_status") or "unknown"),
                )
            )

        completed = EndpointEnrollment(
            **{
                **enrollment.__dict__,
                "status": "completed",
                "completed_at": utcnow_iso(),
            }
        )
        self.enrollments[token] = completed
        self.timeline_events.append(
            TimelineEvent(
                id=str(uuid4()),
                org_id=completed.org_id,
                asset_id=completed.asset_id,
                kind=TimelineKind.AGENT_HEALTH,
                title="Endpoint bootstrap reported",
                body=f"Bootstrap reported {len(agents)} agent states.",
                source="bootstrap",
                details={"agents": agents},
                created_at=utcnow_iso(),
            )
        )
        return {"asset_id": completed.asset_id, "status": completed.status, "agents_reported": len(agents)}

    def _require_org(self, context: TenantContext, org_id: str) -> None:
        if not context.can_access_org(org_id):
            raise AccessDenied(f"user cannot access org: {org_id}")


def seed_store() -> InMemoryControlPlaneStore:
    store = InMemoryControlPlaneStore()
    store.organizations.update(
        {
            "org_acme": Organization(id="org_acme", name="Acme Medical"),
            "org_globex": Organization(id="org_globex", name="Globex Manufacturing"),
        }
    )
    store.assets.update(
        {
            "asset-acme-win-01": Asset(
                id="asset-acme-win-01",
                org_id="org_acme",
                hostname="acme-billing-01",
                operating_system="Windows 11 Pro",
                site="Acme HQ",
                state=AssetState.ACTIVE,
            ),
            "asset-acme-linux-01": Asset(
                id="asset-acme-linux-01",
                org_id="org_acme",
                hostname="acme-file-01",
                operating_system="Ubuntu Server 24.04",
                site="Acme HQ",
                state=AssetState.DEGRADED,
            ),
            "asset-globex-mac-01": Asset(
                id="asset-globex-mac-01",
                org_id="org_globex",
                hostname="globex-design-07",
                operating_system="macOS",
                site="Globex Design",
                state=AssetState.ACTIVE,
            ),
        }
    )

    for asset in store.assets.values():
        for agent in (
            AgentKind.MESHCENTRAL,
            AgentKind.SALT,
            AgentKind.WAZUH,
            AgentKind.ZABBIX,
        ):
            store.connectors.append(
                ConnectorIdentity(
                    asset_id=asset.id,
                    org_id=asset.org_id,
                    connector=agent,
                    external_id=f"{agent.value}:{asset.id}",
                    metadata={"enrollment": "seed"},
                )
            )
            store.agent_health.append(
                AgentHealth(
                    asset_id=asset.id,
                    org_id=asset.org_id,
                    agent=agent,
                    version="seed-0.1",
                    service_state="running",
                    last_seen_at=utcnow_iso(),
                    update_channel="lab",
                    resource_status="normal",
                )
            )

    store.scripts.update(
        {
            "script-disk-cleanup": ScriptDefinition(
                id="script-disk-cleanup",
                org_id=None,
                name="Disk cleanup",
                runtime="powershell/bash",
                revision=1,
                approval_required=False,
            ),
            "script-restart-print-spooler": ScriptDefinition(
                id="script-restart-print-spooler",
                org_id="org_acme",
                name="Restart print spooler",
                runtime="powershell",
                revision=3,
                approval_required=True,
            ),
        }
    )

    for asset in store.assets.values():
        store.timeline_events.append(
            TimelineEvent(
                id=str(uuid4()),
                org_id=asset.org_id,
                asset_id=asset.id,
                kind=TimelineKind.INVENTORY,
                title="Asset enrolled",
                body="Seeded asset graph with MeshCentral, Salt, Wazuh, and Zabbix connector IDs.",
                source="portal",
                details={"connectors": ["meshcentral", "salt", "wazuh", "zabbix"]},
                created_at=utcnow_iso(),
            )
        )

    return store
