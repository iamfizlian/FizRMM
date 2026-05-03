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
