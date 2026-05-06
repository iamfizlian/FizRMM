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
