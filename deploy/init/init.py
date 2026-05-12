from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

from keycloak import KeycloakInit


CONFIG_PATH = Path(os.getenv("FIZRMM_INIT_CONFIG", "/init/config.json"))
OUTPUT_PATH = Path(os.getenv("FIZRMM_INTEGRATIONS_FILE", "/runtime/fizrmm/integrations.json"))
WAIT_TIMEOUT_SECONDS = int(os.getenv("FIZRMM_INIT_WAIT_TIMEOUT", "180"))
DEFAULT_REQUIRED_SERVICES = "keycloak,nats,meshcentral,salt,zabbix,wazuh,opensearch"


SERVICE_PORTS = {
    "keycloak": ("keycloak", 8080),
    "nats": ("nats", 4222),
    "meshcentral": ("meshcentral", 443),
    "salt": ("salt-master", 4505),
    "zabbix": ("zabbix-web", 8080),
    "wazuh": ("wazuh-manager", 55000),
    "opensearch": ("opensearch", 9200),
}


def main() -> None:
    config = read_json(CONFIG_PATH)
    services = selected_service_ports()
    required_services = selected_required_services(services)
    reached_services = wait_for_services(services, required_services)
    mark_service_reachability(config, services, reached_services)
    if "keycloak" in services:
        configure_keycloak(config)
    runtime_config = mark_runtime_config_written(config)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(runtime_config, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote FizRMM runtime integration config to {OUTPUT_PATH}")


def configure_keycloak(config: dict[str, Any]) -> None:
    identity = integration_config(config, "identity")
    if not identity:
        return
    service = identity.setdefault("service", {})
    if not isinstance(service, dict):
        raise ValueError("identity.service must be an object")
    base_url = str(service.get("url") or "http://keycloak:8080")
    public_url = str(service.get("public_url") or os.getenv("KEYCLOAK_PUBLIC_URL", "http://127.0.0.1:8080"))
    realm = str(service.get("realm") or os.getenv("KEYCLOAK_REALM", "fizrmm"))
    client_id = str(service.get("client_id") or os.getenv("OIDC_CLIENT_ID", "fizrmm-portal"))
    admin_user = os.getenv("KEYCLOAK_ADMIN", "admin")
    admin_password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin-dev-password")

    metadata = KeycloakInit(
        base_url=base_url,
        public_url=public_url,
        admin_user=admin_user,
        admin_password=admin_password,
        realm=realm,
        client_id=client_id,
    ).configure()
    service.update(metadata)
    init_state = identity.setdefault("init", {})
    if isinstance(init_state, dict):
        init_state["status"] = "configured"
        init_state["message"] = "Keycloak realm, client, roles, and demo users are configured."
        init_state["keycloak_configured"] = True


def integration_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    integrations = config.get("integrations", {})
    if not isinstance(integrations, dict):
        raise ValueError("init config integrations must be an object")
    integration = integrations.get(name, {})
    return integration if isinstance(integration, dict) else {}


def selected_service_ports() -> dict[str, tuple[str, int]]:
    requested = os.getenv("FIZRMM_INIT_WAIT_SERVICES", ",".join(SERVICE_PORTS))
    names = [name.strip() for name in requested.split(",") if name.strip()]
    return {name: SERVICE_PORTS[name] for name in names if name in SERVICE_PORTS}


def selected_required_services(services: dict[str, tuple[str, int]]) -> set[str]:
    requested = os.getenv("FIZRMM_INIT_REQUIRED_SERVICES", DEFAULT_REQUIRED_SERVICES)
    names = {name.strip() for name in requested.split(",") if name.strip()}
    return {name for name in names if name in services}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        payload = json.load(config_file)
    if not isinstance(payload, dict):
        raise ValueError("init config must be a JSON object")
    return payload


def wait_for_services(
    services: dict[str, tuple[str, int]], required_services: set[str] | None = None
) -> set[str]:
    if required_services is None:
        required_services = set(services)
    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
    pending = dict(services)
    reached: set[str] = set()
    while pending and time.monotonic() < deadline:
        for name, (host, port) in list(pending.items()):
            if can_connect(host, port):
                print(f"{name} is reachable at {host}:{port}")
                reached.add(name)
                del pending[name]
        if pending:
            time.sleep(3)
    missing_required = sorted(name for name in pending if name in required_services)
    if missing_required:
        names = ", ".join(missing_required)
        raise TimeoutError(f"Timed out waiting for required services: {names}")
    if pending:
        names = ", ".join(sorted(pending))
        print(f"Optional services did not become reachable before timeout: {names}")
    return reached


def can_connect(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def mark_service_reachability(
    config: dict[str, Any], services: dict[str, tuple[str, int]], reached_services: set[str]
) -> None:
    service_to_integration = {
        "keycloak": "identity",
        "nats": "nats",
        "meshcentral": "meshcentral",
        "salt": "salt",
        "zabbix": "zabbix",
        "wazuh": "wazuh",
        "opensearch": "opensearch",
    }
    for service_name in services:
        integration = integration_config(config, service_to_integration.get(service_name, service_name))
        if not integration:
            continue
        init_state = integration.setdefault("init", {})
        if isinstance(init_state, dict):
            init_state["service_reachable"] = service_name in reached_services


def mark_runtime_config_written(config: dict[str, Any]) -> dict[str, Any]:
    integrations = config.get("integrations", {})
    if not isinstance(integrations, dict):
        raise ValueError("init config integrations must be an object")
    for integration in integrations.values():
        if not isinstance(integration, dict):
            continue
        init_state = integration.setdefault("init", {})
        if isinstance(init_state, dict):
            init_state["runtime_config_written"] = True
    config["generated_by"] = "fizrmm-init"
    config["generated_at_unix"] = int(time.time())
    return config


if __name__ == "__main__":
    main()
