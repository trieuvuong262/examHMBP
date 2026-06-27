# Cau hinh WebClient registry (can Admin). Map o dia chay o session user thuong.
param(
    [string]$HostName = 'justplay.synology.me',
    [int]$DavPort = 5678
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'JustPlay-NAS-RaiDrive-Setup.ps1')

if (-not (Test-IsAdministrator)) {
    $argList = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
        '-HostName', $HostName, '-DavPort', [string]$DavPort
    )
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $argList
    exit $proc.ExitCode
}

Ensure-WebClientReady -HostName $HostName -DavPort $DavPort
if (-not (Test-WebClientRegistryReady -HostName $HostName -DavPort $DavPort)) {
    exit 1
}
try {
    Restart-Service WebClient -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
} catch {}
exit 0
