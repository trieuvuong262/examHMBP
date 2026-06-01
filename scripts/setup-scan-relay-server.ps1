# Task Scheduler: scan_relay_server.py at logon (no admin required)
#
#   scripts\setup-scan-relay-server.cmd "D:\Project\PortalJustPlay"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [string]$TaskName = "JustPlay-ScanRelayServer"
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path $ProjectDir).Path
$ScriptPath = Join-Path $ProjectDir "scan_relay_server.py"
$EnvPath = Join-Path $ProjectDir "scan_relay.env"

if (-not (Test-Path $ScriptPath)) { throw "scan_relay_server.py not found" }
if (-not (Test-Path $EnvPath)) {
    Write-Warning "scan_relay.env missing - copy from scan_relay.env.example"
}

$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if ($python) { $python = "py.exe" }
}
if (-not $python) { throw "python not found in PATH" }

$taskCmd = if ($python -eq "py.exe") {
    "py.exe `"$ScriptPath`""
} else {
    "`"$python`" `"$ScriptPath`""
}

function Install-StartupShortcut {
    param([string]$Name, [string]$Command, [string]$WorkDir)
    $startup = [Environment]::GetFolderPath("Startup")
    $batPath = Join-Path $startup "$Name.bat"
    @(
        "@echo off",
        "cd /d `"$WorkDir`"",
        "start `"JustPlay Scan Relay`" $Command"
    ) | Set-Content -Path $batPath -Encoding ASCII
    return $batPath
}

# 1) Task cho user hien tai — khong can Admin
try {
    $Action = New-ScheduledTaskAction -Execute $python -Argument "`"$ScriptPath`"" -WorkingDirectory $ProjectDir
    $Trigger = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5) `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Days 0)

    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Settings $Settings -Principal $Principal `
        -Description "JustPlay WMI scan relay (Tailscale :8765)" -Force | Out-Null

    Write-Host "OK: Task '$TaskName' (user $env:USERNAME, no admin)."
    Write-Host "Test: curl http://127.0.0.1:8765/health"
    exit 0
} catch {
    Write-Warning "Scheduled Task failed: $($_.Exception.Message)"
}

# 2) schtasks fallback
try {
    schtasks /Create /TN $TaskName /TR $taskCmd /SC ONLOGON /RL LIMITED /F 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: schtasks '$TaskName' created."
        Write-Host "Test: curl http://127.0.0.1:8765/health"
        exit 0
    }
} catch {
    Write-Warning "schtasks failed: $($_.Exception.Message)"
}

# 3) Startup folder — luon chay duoc khong can Admin
$bat = Install-StartupShortcut -Name $TaskName -Command $taskCmd -WorkDir $ProjectDir
Write-Host "OK: Startup shortcut (no Task Scheduler admin needed):"
Write-Host "  $bat"
Write-Host "Server se chay khi dang nhap Windows. Test tay: python scan_relay_server.py"
Write-Host "VPS .env: EQUIPMENT_RELAY_HTTP_URL=http://<tailscale-ip>:8765"
