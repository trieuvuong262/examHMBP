$ErrorActionPreference = 'Stop'

$RustDeskHost = '__RUSTDESK_HOST__'
$PublicKey = '__PUBLIC_KEY__'

if ($RustDeskHost -like '*__RUSTDESK*') { $RustDeskHost = 'rd.justplay.vn' }
if ($PublicKey -like '*__PUBLIC*') {
    Write-Host 'LOI: Thieu PUBLIC KEY. Tai file tu Portal.'
    exit 1
}

function Find-RustDeskExe {
    foreach ($p in @(
        "${env:ProgramFiles}\RustDesk\rustdesk.exe",
        "${env:ProgramFiles(x86)}\RustDesk\rustdesk.exe",
        "$env:LOCALAPPDATA\RustDesk\rustdesk.exe"
    )) {
        if (Test-Path -LiteralPath $p) { return (Get-Item -LiteralPath $p).FullName }
    }
    return $null
}

function Invoke-RustDeskCli {
    param([string]$Exe, [string[]]$ArgumentList = @(), [int]$TimeoutSec = 15)
    $workDir = Split-Path -Parent $Exe
    $proc = Start-Process -FilePath $Exe -ArgumentList $ArgumentList `
        -WorkingDirectory $workDir -PassThru -WindowStyle Hidden
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return 124
    }
    return $proc.ExitCode
}

function Get-RustDeskConfigDirs {
    $dirs = @()
    if ($env:APPDATA) { $dirs += (Join-Path $env:APPDATA 'RustDesk\config') }
    $serviceDir = 'C:\Windows\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\config'
    if (Test-Path (Split-Path $serviceDir -Parent)) { $dirs += $serviceDir }
    return $dirs | Select-Object -Unique
}

$hostOnly = ($RustDeskHost -replace ':.*$', '').Trim()
$toml = @"
rendezvous_server = '${hostOnly}:21116'
nat_type = 1
serial = 0

[options]
custom-rendezvous-server = '$hostOnly'
relay-server = '${hostOnly}:21117'
api-server = ''
key = '$PublicKey'
"@

Write-Host '========================================'
Write-Host ' JustPlay - Cau hinh RustDesk cho IT'
Write-Host '========================================'
Write-Host ''

$exe = Find-RustDeskExe
if (-not $exe) {
    Write-Host 'LOI: Chua cai RustDesk. Cai tu https://rustdesk.com truoc.'
    exit 1
}

Get-Process -Name 'rustdesk','RustDesk' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
if ($svc) { Stop-Service -Name 'RustDesk' -Force -ErrorAction SilentlyContinue; Start-Sleep 2 }

$utf8 = New-Object System.Text.UTF8Encoding $false
foreach ($dir in (Get-RustDeskConfigDirs)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $path = Join-Path $dir 'RustDesk2.toml'
    [System.IO.File]::WriteAllText($path, $toml, $utf8)
    Write-Host "Da ghi: $path"
}

$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($toml))
Invoke-RustDeskCli -Exe $exe -ArgumentList @('--config', $b64) | Out-Null

if ($svc) {
    Start-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'XONG. Mo RustDesk -> Network: phai hien Ready.'
Write-Host "ID server / Relay: $hostOnly"
Write-Host 'Bay gio co the bam Ket noi tu Portal.'
Write-Host '========================================'
exit 0
