# Chạy scan_relay_server.py lúc khởi động / đăng nhập (portal bấm Quét)
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [string]$TaskName = "JustPlay-ScanRelayServer"
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Resolve-Path $ProjectDir).Path
$ScriptPath = Join-Path $ProjectDir "scan_relay_server.py"
$EnvPath = Join-Path $ProjectDir "scan_relay.env"

if (-not (Test-Path $ScriptPath)) { throw "Không tìm thấy scan_relay_server.py" }
if (-not (Test-Path $EnvPath)) { throw "Chưa có scan_relay.env" }

$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "`"$ScriptPath`"" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME -Delay (New-TimeSpan -Minutes 1)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "HTTP relay WMI cho Portal JustPlay (Tailscale :8765)" -Force | Out-Null

Write-Host "Task '$TaskName' đã tạo. Test: curl http://127.0.0.1:8765/health"
Write-Host "Trên VPS .env: EQUIPMENT_RELAY_HTTP_URL=http://<Tailscale-IP-máy-IT>:8765"
