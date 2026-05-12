from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse
import socket

from .config import load_runtime_config, runtime_config_path
import json

DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "nats": 4222,
    "tcp": 4505,
}

DEFAULT_SERVICE_ENDPOINTS = {
    "identity": ("keycloak", 8080),
    "meshcentral": ("meshcentral", 443),
    "salt": ("salt-master", 4505),
    "zabbix": ("zabbix-web", 8080),
    "wazuh": ("wazuh-manager", 55000),
    "opensearch": ("opensearch", 9200),
    "nats": ("nats", 4222),
}


def service_endpoint(integration_id: str, integration: dict[str, Any]) -> tuple[str, int]:
    service = integration.get("service", {})
    if not isinstance(service, dict):
        service = {}
    raw_url = str(service.get("url") or service.get("api_url") or "").strip()
    parsed = urlparse(raw_url)
    if parsed.hostname:
        return parsed.hostname, parsed.port or DEFAULT_PORTS.get(parsed.scheme, 443)
    return DEFAULT_SERVICE_ENDPOINTS.get(integration_id, (integration_id, 443))


def can_connect(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_runtime_setup(integration_id: str) -> dict[str, Any]:
    """Run the web-initiated deployment setup task for one integration.

    The task validates that the configured backing service endpoint is reachable,
    records deployment metadata in the shared runtime config, and marks the
    integration initialized when the service-level setup can be completed from
    the portal. Deep product-specific bootstrapping can extend this function as
    adapters mature while preserving the same UI/API contract.
    """
    config = load_runtime_config()
    integrations = config.setdefault("integrations", {})
    if not isinstance(integrations, dict):
        integrations = {}
        config["integrations"] = integrations
    integration = integrations.setdefault(integration_id, {})
    if not isinstance(integration, dict):
        integration = {}
        integrations[integration_id] = integration

    init = integration.setdefault("init", {})
    if not isinstance(init, dict):
        init = {}
        integration["init"] = init

    host, port = service_endpoint(integration_id, integration)
    reachable = can_connect(host, port)
    init.update(
        {
            "requested_from": "web_ui",
            "service_host": host,
            "service_port": port,
            "service_reachable": reachable,
            "runtime_config_written": True,
            "last_setup_attempt_unix": int(time.time()),
        }
    )
    if reachable:
        init["status"] = "configured"
        init["message"] = "Deployment setup completed from the FizRMM portal; the backing service endpoint is reachable."
    else:
        init["status"] = "setup_pending"
        init["message"] = (
            "Setup values were saved from the FizRMM portal, but the backing service endpoint "
            f"{host}:{port} is not reachable from the API container yet. Start/connect the service and run setup again."
        )

    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    return integration
