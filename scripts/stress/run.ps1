param(
    [Parameter(Position = 0)]
    [ValidateSet('login', 'reports', 'requests', 'kho-npl', 'mixed', 'help')]
    [string]$Scenario = 'mixed',

    [Parameter(Position = 1)]
    [string]$ExtraArgs = ''
)

$ErrorActionPreference = 'Stop'
$StressDir = $PSScriptRoot
$EnvFile = Join-Path $StressDir 'stress.env'

function Show-StressHelp {
    Write-Host ''
    Write-Host 'Portal JustPlay - k6 stress test' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '  .\run.cmd                    # mixed (mac dinh)'
    Write-Host '  .\run.cmd login              # chi login + trang chu'
    Write-Host '  .\run.cmd reports            # bao cao'
    Write-Host '  .\run.cmd requests           # yeu cau noi bo'
    Write-Host '  .\run.cmd kho-npl            # kho nguyen phu lieu'
    Write-Host '  .\run.cmd mixed              # tron 3 module'
    Write-Host ''
    Write-Host 'Cau hinh: copy stress.env.example -> stress.env'
    Write-Host 'Theo doi VPS: ..\..\monitor.cmd watch'
    Write-Host ''
}

if ($Scenario -eq 'help') {
    Show-StressHelp
    exit 0
}

if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
    Write-Host 'Chua cai k6. Cai bang:' -ForegroundColor Yellow
    Write-Host '  winget install k6 --source winget'
    Write-Host '  hoac: choco install k6'
    Write-Host '  hoac: https://grafana.com/docs/k6/latest/set-up/install-k6/'
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "Thieu file $EnvFile" -ForegroundColor Yellow
    Write-Host 'Chay: copy stress.env.example stress.env roi dien STRESS_USER / STRESS_PASS'
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $eq = $line.IndexOf('=')
    if ($eq -lt 1) { return }
    $key = $line.Substring(0, $eq).Trim()
    $val = $line.Substring($eq + 1).Trim()
    if ($val.StartsWith('"') -and $val.EndsWith('"')) {
        $val = $val.Substring(1, $val.Length - 2)
    }
    Set-Item -Path "env:$key" -Value $val
}

if (-not $env:STRESS_USER -or -not $env:STRESS_PASS) {
    Write-Host 'stress.env can STRESS_USER va STRESS_PASS' -ForegroundColor Red
    exit 1
}

$scriptFile = Join-Path $StressDir "$Scenario.js"
if (-not (Test-Path $scriptFile)) {
    Write-Host "Khong tim thay kich ban: $scriptFile" -ForegroundColor Red
    exit 1
}

$baseUrl = if ($env:STRESS_BASE_URL) { $env:STRESS_BASE_URL } else { 'https://portal.justplay.vn' }
$vus = if ($env:STRESS_VUS) { $env:STRESS_VUS } else { '10' }
$duration = if ($env:STRESS_DURATION) { $env:STRESS_DURATION } else { '3m' }

Write-Host ''
Write-Host "k6 stress: $Scenario" -ForegroundColor Cyan
Write-Host "  URL: $baseUrl"
Write-Host "  VUs: $vus  |  Duration: $duration"
Write-Host ''

Push-Location $StressDir
try {
    $k6Args = @('run', $scriptFile)
    if ($ExtraArgs) {
        $k6Args += $ExtraArgs.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
    }
    & k6 @k6Args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
