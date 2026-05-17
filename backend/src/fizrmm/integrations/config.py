from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_CONFIG_PATH = "/runtime/fizrmm/integrations.json"


def runtime_config_path() -> Path:
    return Path(os.getenv("FIZRMM_INTEGRATIONS_FILE", DEFAULT_RUNTIME_CONFIG_PATH))


def load_runtime_config() -> dict[str, Any]:
    path = runtime_config_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as config_file:
        payload = json.load(config_file)
    return payload if isinstance(payload, dict) else {}


def runtime_integration(name: str) -> dict[str, Any]:
    integrations = load_runtime_config().get("integrations", {})
    value = integrations.get(name) if isinstance(integrations, dict) else None
    return value if isinstance(value, dict) else {}


def runtime_bootstrap_value(name: str, key: str, default: str = "") -> str:
    integration = runtime_integration(name)
    bootstrap = integration.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return default
    return str(bootstrap.get(key) or default)


def runtime_service_value(name: str, key: str, default: str = "") -> str:
    integration = runtime_integration(name)
    service = integration.get("service", {})
    if not isinstance(service, dict):
        return default
    return str(service.get(key) or default)


def save_runtime_integration(name: str, service: dict[str, Any], bootstrap: dict[str, Any]) -> dict[str, Any]:
    config = load_runtime_config()
    integrations = config.setdefault("integrations", {})
    if not isinstance(integrations, dict):
        integrations = {}
        config["integrations"] = integrations
    integration = integrations.setdefault(name, {})
    if not isinstance(integration, dict):
        integration = {}
        integrations[name] = integration
    existing_service = integration.setdefault("service", {})
    if not isinstance(existing_service, dict):
        existing_service = {}
        integration["service"] = existing_service
    existing_bootstrap = integration.setdefault("bootstrap", {})
    if not isinstance(existing_bootstrap, dict):
        existing_bootstrap = {}
        integration["bootstrap"] = existing_bootstrap
    for key, value in service.items():
        existing_service[key] = value
    for key, value in bootstrap.items():
        existing_bootstrap[key] = value
    init = integration.setdefault("init", {})
    if isinstance(init, dict):
        init["status"] = "configured"
        init["message"] = "Integration runtime config is active."
        init["runtime_config_written"] = True
    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    return integration
