from __future__ import annotations


def render_windows_bootstrap(portal_url: str, token: str) -> str:
    return f"""param(
    [string]$PortalUrl = "{portal_url}",
    [string]$EnrollmentToken = "{token}"
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {{
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {{
        throw "FizRMM bootstrap must be run from an elevated PowerShell session."
    }}
}}

function Invoke-FizRmmJson {{
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body
    )
    $uri = "$PortalUrl$Path"
    $json = $Body | ConvertTo-Json -Depth 8
    Invoke-RestMethod -Method $Method -Uri $uri -ContentType "application/json" -Body $json
}}

function Install-AgentPackage {{
    param(
        [string]$Agent,
        [string]$InstallerUrl,
        [string]$InstallArgs
    )

    if ([string]::IsNullOrWhiteSpace($InstallerUrl)) {{
        Write-Host "Skipping $Agent because no installer URL was provided by the portal."
        return @{{
            agent = $Agent
            status = "skipped_no_installer_url"
            version = "unknown"
            external_id = "$($Agent):$env:COMPUTERNAME"
        }}
    }}

    $extension = [IO.Path]::GetExtension(([Uri]$InstallerUrl).AbsolutePath)
    if ([string]::IsNullOrWhiteSpace($extension)) {{
        $extension = ".exe"
    }}
    $target = Join-Path $env:TEMP "fizrmm-$Agent$extension"
    Write-Host "Downloading $Agent from $InstallerUrl"
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $target

    if ([string]::IsNullOrWhiteSpace($InstallArgs)) {{
        if ($extension -eq ".msi") {{
            $process = Start-Process msiexec.exe -ArgumentList "/i `"$target`" /qn /norestart" -Wait -PassThru
        }} else {{
            $process = Start-Process $target -ArgumentList "/quiet /norestart" -Wait -PassThru
        }}
    }} else {{
        $expandedArgs = $InstallArgs.Replace("{{INSTALLER_PATH}}", $target)
        $process = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"$expandedArgs`"" -Wait -PassThru
    }}

    if ($process.ExitCode -ne 0) {{
        throw "$Agent installer exited with code $($process.ExitCode)"
    }}

    return @{{
        agent = $Agent
        status = "installed"
        version = "unknown"
        external_id = "$($Agent):$env:COMPUTERNAME"
    }}
}}

Assert-Administrator
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$os = Get-CimInstance Win32_OperatingSystem
$claim = Invoke-FizRmmJson -Method "POST" -Path "/api/enrollments/$EnrollmentToken/claim" -Body @{{
    hostname = $env:COMPUTERNAME
    operating_system = $os.Caption
}}

Write-Host "Claimed FizRMM enrollment for asset $($claim.asset_id)"
$config = $claim.config
$agentReports = @()

$agentReports += Install-AgentPackage -Agent "meshcentral" -InstallerUrl $config.meshcentral.installer_url -InstallArgs $config.meshcentral.install_args
$agentReports += Install-AgentPackage -Agent "zabbix" -InstallerUrl $config.zabbix.installer_url -InstallArgs $config.zabbix.install_args
$agentReports += Install-AgentPackage -Agent "wazuh" -InstallerUrl $config.wazuh.installer_url -InstallArgs $config.wazuh.install_args
$agentReports += Install-AgentPackage -Agent "salt" -InstallerUrl $config.salt.installer_url -InstallArgs $config.salt.install_args

$report = Invoke-FizRmmJson -Method "POST" -Path "/api/enrollments/$EnrollmentToken/report" -Body @{{
    agents = $agentReports
}}

Write-Host "FizRMM bootstrap complete for asset $($report.asset_id). Agents reported: $($report.agents_reported)"
"""


def render_linux_bootstrap(portal_url: str, token: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

PORTAL_URL="${{PORTAL_URL:-{portal_url}}}"
ENROLLMENT_TOKEN="${{ENROLLMENT_TOKEN:-{token}}}"

if [ "${{EUID:-$(id -u)}}" -ne 0 ]; then
  echo "FizRMM bootstrap must be run as root. Re-run with sudo." >&2
  exit 1
fi

need_cmd() {{
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}}

need_cmd curl
need_cmd python3

json_post() {{
  local path="$1"
  local body="$2"
  curl -fsS \
    -H 'Content-Type: application/json' \
    -X POST \
    -d "$body" \
    "$PORTAL_URL$path"
}}

json_get() {{
  local expression="$1"
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(eval(sys.argv[1], {{}}, {{"data": data}}) or "")' "$expression"
}}

json_string() {{
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}}

HOSTNAME_VALUE="$(hostname -f 2>/dev/null || hostname)"
OS_VALUE="$(. /etc/os-release 2>/dev/null && echo "${{PRETTY_NAME:-Linux}}" || uname -s)"
CLAIM_BODY="{{\"hostname\":$(json_string "$HOSTNAME_VALUE"),\"operating_system\":$(json_string "$OS_VALUE")}}"
CLAIM_RESPONSE="$(json_post "/api/enrollments/$ENROLLMENT_TOKEN/claim" "$CLAIM_BODY")"
ASSET_ID="$(printf '%s' "$CLAIM_RESPONSE" | json_get 'data.get("asset_id", "")')"

echo "Claimed FizRMM enrollment for asset $ASSET_ID"

install_agent() {{
  local agent="$1"
  local url_expr="$2"
  local args_expr="$3"
  local installer_url install_args target status
  installer_url="$(printf '%s' "$CLAIM_RESPONSE" | json_get "$url_expr")"
  install_args="$(printf '%s' "$CLAIM_RESPONSE" | json_get "$args_expr")"

  if [ -z "$installer_url" ]; then
    echo "Skipping $agent because no Linux installer URL was provided by the portal." >&2
    status="skipped_no_installer_url"
  else
    target="/tmp/fizrmm-$agent-installer"
    echo "Downloading $agent from $installer_url" >&2
    curl -fL "$installer_url" -o "$target"
    chmod +x "$target"
    if [ -n "$install_args" ]; then
      INSTALLER_PATH="$target" sh -c "$install_args"
    else
      "$target"
    fi
    status="installed"
  fi

  python3 -c 'import json,sys; print(json.dumps({{"agent": sys.argv[1], "status": sys.argv[2], "version": "unknown", "external_id": f"{{sys.argv[1]}}:{{sys.argv[3]}}"}}))' "$agent" "$status" "$HOSTNAME_VALUE"
}}

AGENT_REPORTS="$(
  python3 -c 'import json,sys; print(json.dumps([json.loads(line) for line in sys.stdin if line.strip()]))' <<EOF
$(install_agent meshcentral 'data.get("config", {{}}).get("meshcentral", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("meshcentral", {{}}).get("linux_install_args", "")')
$(install_agent zabbix 'data.get("config", {{}}).get("zabbix", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("zabbix", {{}}).get("linux_install_args", "")')
$(install_agent wazuh 'data.get("config", {{}}).get("wazuh", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("wazuh", {{}}).get("linux_install_args", "")')
$(install_agent salt 'data.get("config", {{}}).get("salt", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("salt", {{}}).get("linux_install_args", "")')
EOF
)"

REPORT_BODY="$(python3 -c 'import json,sys; print(json.dumps({{"agents": json.loads(sys.stdin.read())}}))' <<<"$AGENT_REPORTS")"
REPORT_RESPONSE="$(json_post "/api/enrollments/$ENROLLMENT_TOKEN/report" "$REPORT_BODY")"
REPORTED_COUNT="$(printf '%s' "$REPORT_RESPONSE" | json_get 'data.get("agents_reported", "")')"

echo "FizRMM Linux bootstrap complete for asset $ASSET_ID. Agents reported: $REPORTED_COUNT"
"""
