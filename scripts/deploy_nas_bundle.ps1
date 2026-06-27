# Deploy nhanh goi NAS (EXE + PS1 + views) len VPS khi SSH hoat dong.
# Chay: powershell -ExecutionPolicy Bypass -File scripts/deploy_nas_bundle.ps1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Project = Split-Path -Parent $Root
Set-Location $Project

$envFile = Join-Path $Project 'deploy.local.env'
$host_ = '103.90.224.203'
$user = 'root'
$port = '22'
$remote = '/opt/portaljustplay'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*VPS_HOST=(.+)$') { $host_ = $Matches[1].Trim() }
        if ($_ -match '^\s*VPS_USER=(.+)$') { $user = $Matches[1].Trim() }
        if ($_ -match '^\s*VPS_PORT=(.+)$') { $port = $Matches[1].Trim() }
        if ($_ -match '^\s*PROJECT_DIR=(.+)$') { $remote = $Matches[1].Trim() }
    }
}

$files = @(
    'scripts/Ket-Noi-NAS-JustPlay.exe',
    'scripts/JustPlay-NAS-RaiDrive-Setup.ps1',
    'scripts/Prepare-JustPlay-WebClient.ps1',
    'scripts/JustPlay-RustDesk-Setup.ps1',
    'scripts/JustPlay-Equipment-Scan.ps1',
    'scripts/JustPlay-NAS-Launcher.cs',
    'scripts/vps_test_nas_library.py',
    'nas_storage/views_nas_download.py',
    'nas_storage/templates/nas_storage/nas_download.html'
)

foreach ($rel in $files) {
    $local = Join-Path $Project $rel
    if (-not (Test-Path -LiteralPath $local)) {
        throw "Thieu file: $local"
    }
}

Write-Host "==> Validate NAS PS1 local"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'test_nas_ps1_validate.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> SSH ${user}@${host_}:${port} -> git pull + copy into web container + restart"
$copyLines = ($files | ForEach-Object { "docker cp '$remote/$_' portaljustplay-web-1:/app/$_" }) -join "`n"
$remoteCmd = @"
set -Eeuo pipefail
cd '$remote'
git fetch origin main
git reset --hard origin/main
$copyLines
docker compose restart web
sleep 3
docker compose exec -T web python scripts/vps_test_nas_library.py
"@

& ssh -p $port "${user}@${host_}" $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "SSH that bai. Code da push len GitHub - khi VPS online chay lai script nay hoac ./deploy.sh tren VPS."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "OK: NAS bundle tren VPS. Tai ZIP: https://portal.justplay.vn/thu-muc-nas/cai-dat/tai/"
