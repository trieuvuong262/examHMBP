# Install JustPlay Agent — Task at logon (no admin if possible)
param(
    [Parameter(Mandatory = $true)]
    [string]$AgentDir,

    [string]$TaskName = "JustPlay-Agent"
)

$ErrorActionPreference = "Stop"
$AgentDir = (Resolve-Path $AgentDir).Path
$Exe = Join-Path $AgentDir "JustPlayAgent.exe"
$Ini = Join-Path $AgentDir "justplay_agent.ini"

if (-not (Test-Path $Exe)) { throw "JustPlayAgent.exe not found in $AgentDir" }
if (-not (Test-Path $Ini)) { throw "justplay_agent.ini not found - copy from justplay_agent.ini.example" }

$Action = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory $AgentDir
$Trigger = New-ScheduledTaskTrigger -AtLogon
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal `
    -Description "JustPlay Agent - bao cao thiet bi len portal" -Force | Out-Null

Write-Host "Task $TaskName created. Test: & '$Exe' --once"
