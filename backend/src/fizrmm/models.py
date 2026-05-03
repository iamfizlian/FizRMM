from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AgentKind(StrEnum):
    MESHCENTRAL = "meshcentral"
    SALT = "salt"
    WAZUH = "wazuh"
    ZABBIX = "zabbix"
    OSQUERY = "osquery"
    FLUENT_BIT = "fluent_bit"


class AssetState(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class TimelineKind(StrEnum):
    AGENT_HEALTH = "agent_health"
    ALERT = "alert"
    ENROLLMENT = "enrollment"
    AUDIT = "audit"
    INVENTORY = "inventory"
    REMOTE_SESSION = "remote_session"
    SCRIPT_RUN = "script_run"


class AccessDenied(Exception):
    """Raised when tenant context does not allow access to an object."""


class NotFound(Exception):
    """Raised when a requested domain object does not exist."""


@dataclass(frozen=True)
class TenantContext:
    user_id: str
    allowed_org_ids: tuple[str, ...]
    role: str = "technician"
    platform_admin: bool = False

    def can_access_org(self, org_id: str) -> bool:
        return self.platform_admin or org_id in self.allowed_org_ids


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    status: str = "active"


@dataclass(frozen=True)
class Asset:
    id: str
    org_id: str
    hostname: str
    operating_system: str
    site: str
    state: AssetState


@dataclass(frozen=True)
class ConnectorIdentity:
    asset_id: str
    org_id: str
    connector: AgentKind
    external_id: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AgentHealth:
    asset_id: str
    org_id: str
    agent: AgentKind
    version: str
    service_state: str
    last_seen_at: str
    update_channel: str
    resource_status: str


@dataclass(frozen=True)
class ScriptDefinition:
    id: str
    org_id: str | None
    name: str
    runtime: str
    revision: int
    approval_required: bool


@dataclass(frozen=True)
class AuditEvent:
    id: str
    org_id: str
    actor_user_id: str
    action: str
    asset_id: str | None
    result: str
    details: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class TimelineEvent:
    id: str
    org_id: str
    asset_id: str
    kind: TimelineKind
    title: str
    body: str
    source: str
    details: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class EndpointEnrollment:
    id: str
    org_id: str
    site: str
    token: str
    status: str
    created_by: str
    asset_id: str | None
    expires_at: str
    claimed_at: str | None
    completed_at: str | None
    config: dict[str, Any]


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def to_jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return str(value)
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value
