# Deploy nhanh goi Cong cu IT (EXE + scripts + views) len VPS khi SSH hoat dong.
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
    'scripts/Mo-Ket-Noi-NAS.ps1',
    'scripts/Chay-Ket-Noi-NAS.bat',
    'scripts/KET-NOI-NAS.bat',
    'scripts/JustPlay-Cong-Cu-IT-Ubuntu.sh',
    'scripts/JustPlay-RustDesk-Setup.ps1',
    'scripts/JustPlay-RustDesk-Setup.sh',
    'scripts/JustPlay-RaiDrive-Setup.sh',
    'scripts/JustPlay-Equipment-Scan.ps1',
    'scripts/JustPlay-Equipment-Scan.sh',
    'scripts/JustPlay-NAS-Launcher.cs',
    'scripts/vps_test_nas_library.py',
    'nas_storage/views_nas_download.py',
    'nas_storage/ubuntu_deb_packager.py',
    'nas_storage/templates/nas_storage/nas_download.html',
    'templates/includes/portal_header.html'
)

foreach ($rel in $files) {
    $local = Join-Path $Project $rel
    if (-not (Test-Path -LiteralPath $local)) {
        throw "Thieu file: $local"
    }
}

Write-Host "==> Build launcher EXE"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'build_nas_launcher.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> SCP file local -> ${user}@${host_}:${remote}"
# scp tung file (giu dung path tren VPS)
foreach ($rel in $files) {
    $local = Join-Path $Project $rel
    $remoteDir = Split-Path -Parent "$remote/$rel"
    & ssh -p $port "${user}@${host_}" "mkdir -p '$remoteDir'"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & scp -P $port $local "${user}@${host_}:${remote}/$rel"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "    OK $rel"
}

Write-Host "==> docker cp vao web container + restart + test"
$copyLines = ($files | ForEach-Object { "docker cp '$remote/$_' portaljustplay-web-1:/app/$_" }) -join "`n"
$remoteCmd = @"
set -Eeuo pipefail
cd '$remote'
$copyLines
docker compose restart web
sleep 3
docker compose exec -T web python scripts/vps_test_nas_library.py
"@

& ssh -p $port "${user}@${host_}" $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "SSH that bai. Khi VPS online chay lai script nay."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "OK: Cong cu IT tren VPS. Tai DEB: https://portal.justplay.vn/tai-lieu/tai-nas/"
