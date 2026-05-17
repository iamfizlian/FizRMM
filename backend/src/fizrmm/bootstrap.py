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
  local response status
  response="$(curl -sS \
    -H 'Content-Type: application/json' \
    -X POST \
    -d "$body" \
    -w '\n%{{http_code}}' \
    "$PORTAL_URL$path")"
  status="${{response##*$'\n'}}"
  response="${{response%$'\n'*}}"
  if [ "$status" -lt 200 ] || [ "$status" -ge 300 ]; then
    echo "FizRMM API $path failed with HTTP $status: $response" >&2
    exit 1
  fi
  printf '%s' "$response"
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
CLAIM_BODY="$(python3 -c 'import json,sys; print(json.dumps({{"hostname": sys.argv[1], "operating_system": sys.argv[2]}}))' "$HOSTNAME_VALUE" "$OS_VALUE")"
CLAIM_RESPONSE="$(json_post "/api/enrollments/$ENROLLMENT_TOKEN/claim" "$CLAIM_BODY")"
ASSET_ID="$(printf '%s' "$CLAIM_RESPONSE" | json_get 'data.get("asset_id", "")')"
LOG_FILE="${{FIZRMM_BOOTSTRAP_LOG:-/var/log/fizrmm-bootstrap-${{ASSET_ID:-unknown}}.log}}"
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

echo "Claimed FizRMM enrollment for asset $ASSET_ID"
echo "Detailed installer log: $LOG_FILE"

INSTALL_BUILTIN_AGENTS="${{FIZRMM_INSTALL_BUILTIN_AGENTS:-true}}"

log_step() {{
  printf '[FizRMM] %s\n' "$*" >&2
  printf '[%s] %s\n' "$(date -Is 2>/dev/null || date)" "$*" >> "$LOG_FILE"
}}

log_error_tail() {{
  local agent="$1"
  echo "[FizRMM] $agent failed. Last installer log lines:"
  tail -n 20 "$LOG_FILE" | sed 's/^/[FizRMM log] /'
}}

agent_report() {{
  python3 -c 'import json,sys; print(json.dumps({{"agent": sys.argv[1], "status": sys.argv[2], "version": "unknown", "external_id": f"{{sys.argv[1]}}:{{sys.argv[3]}}"}}))' "$1" "$2" "$HOSTNAME_VALUE"
}}

service_enable_now() {{
  local service="$1"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now "$service"
  elif command -v service >/dev/null 2>&1; then
    service "$service" restart
  fi
}}

package_install() {{
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get -qq update
    apt-get install -y -qq "$@"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q "$@"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y -q "$@"
  elif command -v zypper >/dev/null 2>&1; then
    zypper --quiet --non-interactive install "$@"
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --needed --noconfirm "$@"
  else
    echo "No supported package manager found for $*" >&2
    return 1
  fi
}}

config_set() {{
  local file="$1"
  local key="$2"
  local value="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  if grep -qE "^#?${{key}}=" "$file"; then
    sed -i "s|^#\\?${{key}}=.*|${{key}}=${{value}}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}}

install_zabbix_builtin() {{
  local server
  server="$(printf '%s' "$CLAIM_RESPONSE" | json_get 'data.get("config", {{}}).get("zabbix", {{}}).get("server_url", "")')"
  if [ -z "$server" ]; then
    echo "Zabbix server URL is missing from enrollment config." >&2
    return 1
  fi
  if ! command -v zabbix_agent2 >/dev/null 2>&1; then
    package_install zabbix-agent2 || package_install zabbix-agent
  fi
  if [ -f /etc/zabbix/zabbix_agent2.conf ] || command -v zabbix_agent2 >/dev/null 2>&1; then
    config_set /etc/zabbix/zabbix_agent2.conf Server "$server"
    config_set /etc/zabbix/zabbix_agent2.conf ServerActive "$server"
    config_set /etc/zabbix/zabbix_agent2.conf Hostname "$HOSTNAME_VALUE"
    service_enable_now zabbix-agent2
  else
    config_set /etc/zabbix/zabbix_agentd.conf Server "$server"
    config_set /etc/zabbix/zabbix_agentd.conf ServerActive "$server"
    config_set /etc/zabbix/zabbix_agentd.conf Hostname "$HOSTNAME_VALUE"
    service_enable_now zabbix-agent
  fi
}}

install_wazuh_builtin() {{
  local manager
  manager="$(printf '%s' "$CLAIM_RESPONSE" | json_get 'data.get("config", {{}}).get("wazuh", {{}}).get("manager_url", "")')"
  if [ -z "$manager" ]; then
    echo "Wazuh manager URL is missing from enrollment config." >&2
    return 1
  fi
  if [ ! -x /var/ossec/bin/wazuh-control ]; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update
      apt-get install -y gnupg
      curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | gpg --dearmor -o /usr/share/keyrings/wazuh.gpg
      echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" > /etc/apt/sources.list.d/wazuh.list
      apt-get update
      WAZUH_MANAGER="$manager" apt-get install -y wazuh-agent
    elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
      cat > /etc/yum.repos.d/wazuh.repo <<'REPO'
[wazuh]
gpgcheck=1
gpgkey=https://packages.wazuh.com/key/GPG-KEY-WAZUH
enabled=1
name=EL-$releasever - Wazuh
baseurl=https://packages.wazuh.com/4.x/yum/
protect=1
REPO
      if command -v dnf >/dev/null 2>&1; then
        WAZUH_MANAGER="$manager" dnf install -y wazuh-agent
      else
        WAZUH_MANAGER="$manager" yum install -y wazuh-agent
      fi
    else
      echo "No precompiled Wazuh agent package is configured for this distribution. Set WAZUH_LINUX_AGENT_INSTALLER_URL to a prebuilt package or installer." >&2
      return 1
    fi
  fi
  if [ -f /var/ossec/etc/ossec.conf ]; then
    python3 - "$manager" <<'WAZUHCFG'
import sys
import xml.etree.ElementTree as ET
path = "/var/ossec/etc/ossec.conf"
manager = sys.argv[1]
tree = ET.parse(path)
root = tree.getroot()
client = root.find("client")
if client is None:
    client = ET.SubElement(root, "client")
server = client.find("server")
if server is None:
    server = ET.SubElement(client, "server")
address = server.find("address")
if address is None:
    address = ET.SubElement(server, "address")
address.text = manager
tree.write(path)
WAZUHCFG
  fi
  service_enable_now wazuh-agent
}}

install_salt_builtin() {{
  local master
  master="$(printf '%s' "$CLAIM_RESPONSE" | json_get 'data.get("config", {{}}).get("salt", {{}}).get("master_url", "")')"
  if [ -z "$master" ]; then
    echo "Salt master URL is missing from enrollment config." >&2
    return 1
  fi
  if ! command -v salt-minion >/dev/null 2>&1; then
    if package_install salt-minion || package_install salt; then
      true
    else
      echo "No precompiled Salt minion package is configured for this distribution. Set SALT_LINUX_MINION_INSTALLER_URL to a prebuilt package or installer." >&2
      return 1
    fi
  fi
  if ! command -v salt-minion >/dev/null 2>&1; then
    echo "Salt minion was not installed by any supported installer path." >&2
    return 1
  fi
  mkdir -p /etc/salt/minion.d
  printf 'master: %s\nid: %s\n' "$master" "$HOSTNAME_VALUE" > /etc/salt/minion.d/fizrmm.conf
  service_enable_now salt-minion
}}

install_builtin_agent() {{
  local agent="$1"
  local installer_fn="$2"
  local status
  if [ "$INSTALL_BUILTIN_AGENTS" != "true" ]; then
    log_step "Skipping $agent built-in installer because FIZRMM_INSTALL_BUILTIN_AGENTS=$INSTALL_BUILTIN_AGENTS."
    agent_report "$agent" "skipped_builtin_disabled"
    return 0
  fi
  log_step "Installing $agent with the built-in Linux installer."
  set +e
  "$installer_fn" >> "$LOG_FILE" 2>&1
  local rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    status="installed"
    log_step "$agent installed."
  else
    status="failed_install"
    log_step "$agent failed with exit code $rc."
    log_error_tail "$agent" >&2
  fi
  agent_report "$agent" "$status"
}}

install_agent() {{
  local agent="$1"
  local url_expr="$2"
  local args_expr="$3"
  local insecure_expr="${{4:-}}"
  local builtin_fn="${{5:-}}"
  local installer_url install_args insecure_tls curl_flags target status
  installer_url="$(printf '%s' "$CLAIM_RESPONSE" | json_get "$url_expr")"
  install_args="$(printf '%s' "$CLAIM_RESPONSE" | json_get "$args_expr")"
  insecure_tls="false"
  if [ -n "$insecure_expr" ]; then
    insecure_tls="$(printf '%s' "$CLAIM_RESPONSE" | json_get "$insecure_expr")"
  fi

  if [ -z "$installer_url" ]; then
    if [ -n "$builtin_fn" ]; then
      install_builtin_agent "$agent" "$builtin_fn"
      return 0
    fi
    log_step "Skipping $agent because no Linux installer URL was provided by the portal."
    status="skipped_no_installer_url"
  else
    target="/tmp/fizrmm-$agent-installer"
    log_step "Downloading $agent installer."
    printf '[%s] %s installer URL: %s\n' "$(date -Is 2>/dev/null || date)" "$agent" "$installer_url" >> "$LOG_FILE"
    curl_flags="-fL"
    if [ "$insecure_tls" = "true" ]; then
      curl_flags="-fkL"
    fi
    set +e
    curl $curl_flags "$installer_url" -o "$target" >> "$LOG_FILE" 2>&1 && chmod +x "$target"
    local download_rc=$?
    if [ "$download_rc" -eq 0 ]; then
      if [ -n "$install_args" ]; then
        INSTALLER_PATH="$target" sh -c "$install_args" >> "$LOG_FILE" 2>&1
      else
        "$target" >> "$LOG_FILE" 2>&1
      fi
    fi
    local install_rc=$?
    set -e
    if [ "$download_rc" -eq 0 ] && [ "$install_rc" -eq 0 ]; then
      status="installed"
      log_step "$agent installed."
    else
      status="failed_install"
      log_step "$agent failed. download_rc=$download_rc install_rc=$install_rc."
      log_error_tail "$agent" >&2
    fi
  fi

  agent_report "$agent" "$status"
}}

AGENT_REPORTS="$(
  python3 -c 'import json,sys
reports = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        reports.append(json.loads(line))
    except json.JSONDecodeError:
        print(f"Ignoring non-JSON installer output while building report: {{line}}", file=sys.stderr)
print(json.dumps(reports))' <<EOF
$(install_agent meshcentral 'data.get("config", {{}}).get("meshcentral", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("meshcentral", {{}}).get("linux_install_args", "")' 'str(data.get("config", {{}}).get("meshcentral", {{}}).get("linux_insecure_tls", "false")).lower()')
$(install_agent zabbix 'data.get("config", {{}}).get("zabbix", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("zabbix", {{}}).get("linux_install_args", "")' '' install_zabbix_builtin)
$(install_agent wazuh 'data.get("config", {{}}).get("wazuh", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("wazuh", {{}}).get("linux_install_args", "")' '' install_wazuh_builtin)
$(install_agent salt 'data.get("config", {{}}).get("salt", {{}}).get("linux_installer_url", "")' 'data.get("config", {{}}).get("salt", {{}}).get("linux_install_args", "")' '' install_salt_builtin)
EOF
)"

REPORT_BODY="$(python3 -c 'import json,sys; print(json.dumps({{"agents": json.loads(sys.stdin.read())}}))' <<<"$AGENT_REPORTS")"
REPORT_RESPONSE="$(json_post "/api/enrollments/$ENROLLMENT_TOKEN/report" "$REPORT_BODY")"
REPORTED_COUNT="$(printf '%s' "$REPORT_RESPONSE" | json_get 'data.get("agents_reported", "")')"

echo "FizRMM agent install summary:"
printf '%s' "$AGENT_REPORTS" | python3 -c 'import json,sys
for item in json.load(sys.stdin):
    print("  - {{}}: {{}}".format(item.get("agent", "unknown"), item.get("status", "unknown")))
'
echo "Detailed installer log: $LOG_FILE"
echo "FizRMM Linux bootstrap complete for asset $ASSET_ID. Agents reported: $REPORTED_COUNT"
"""
