from __future__ import annotations

import shlex
from collections.abc import Mapping

from .models import EndpointEnrollment


def _powershell_single_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def enrollment_bootstrap_payload(
    enrollment: EndpointEnrollment,
    token: str,
    config: Mapping[str, object],
) -> dict[str, object]:
    portal_url = str(config.get("portal_url") or "").rstrip("/")
    windows_bootstrap_url = f"/api/enrollments/{token}/bootstrap.ps1"
    linux_bootstrap_url = f"/api/enrollments/{token}/bootstrap.sh"
    linux_download_url = f"{portal_url}{linux_bootstrap_url}" if portal_url else linux_bootstrap_url

    return {
        "enrollment": enrollment,
        "token": token,
        "bootstrap_url": windows_bootstrap_url,
        "linux_bootstrap_url": linux_bootstrap_url,
        "command": (
            "powershell.exe -ExecutionPolicy Bypass -File .\\fizrmm-bootstrap.ps1 "
            f"-PortalUrl {_powershell_single_quote(portal_url)} -EnrollmentToken {_powershell_single_quote(token)}"
        ),
        "linux_command": (
            f"curl -fsSL {shlex.quote(linux_download_url)} "
            "-o fizrmm-bootstrap.sh && sudo bash ./fizrmm-bootstrap.sh"
        ),
    }
