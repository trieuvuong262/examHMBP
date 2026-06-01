# Đăng ký Task Scheduler — quét thiết bị tự động trên máy Windows IT
# Cách 1: scripts\setup-scan-relay-task.cmd "D:\Project\PortalJustPlay"
# Cách 2: Set-ExecutionPolicy -Scope Process Bypass rồi chạy .ps1

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [string]$TaskName = "JustPlay-ScanRelay",

    [int]$IntervalHours = 2,

    [int]$LogonDelayMinutes = 2
)

$ErrorActionPreference = "Stop"

$ProjectDir = (Resolve-Path $ProjectDir).Path
$ScriptPath = Join-Path $ProjectDir "scan_relay.py"
$EnvPath = Join-Path $ProjectDir "scan_relay.env"

if (-not (Test-Path $ScriptPath)) {
    throw "Không tìm thấy scan_relay.py tại $ScriptPath"
}
if (-not (Test-Path $EnvPath)) {
    throw "Chưa có scan_relay.env — copy từ scan_relay.env.example và điền cấu hình."
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command py -ErrorAction SilentlyContinue).Source
    if ($python) { $python = "$python -3" }
}
if (-not $python) {
    throw "Không tìm thấy python trong PATH."
}

$Action = New-ScheduledTaskAction `
    -Execute "python.exe" `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $ProjectDir

$TriggerLogon = New-ScheduledTaskTrigger -AtLogon

$StartTime = (Get-Date).Date.AddHours(8)
$TriggerRepeat = New-ScheduledTaskTrigger -Once -At $StartTime `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($TriggerLogon, $TriggerRepeat) `
    -Settings $Settings `
    -Description "Quét WMI LAN → Portal JustPlay (scan_relay.py)" `
    -Force | Out-Null

Write-Host "Đã tạo task '$TaskName':"
Write-Host "  - Khi đăng nhập Windows (delay ${LogonDelayMinutes} phút)"
Write-Host "  - Lặp mỗi ${IntervalHours} giờ"
Write-Host "Test: python `"$ScriptPath`" --dry-run"
