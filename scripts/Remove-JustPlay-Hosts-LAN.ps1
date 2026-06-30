# Xoa dong hosts ep justplay.synology.me -> 192.168.1.254 (gay WebDAV/RaiDrive 401).
# Chay: chuot phai PowerShell -> Run as administrator
#   powershell -ExecutionPolicy Bypass -File Remove-JustPlay-Hosts-LAN.ps1

$ErrorActionPreference = 'Stop'
$hostsPath = Join-Path $env:windir 'System32\drivers\etc\hosts'

if (-not (Test-Path -LiteralPath $hostsPath)) {
    Write-Host "Khong tim thay: $hostsPath" -ForegroundColor Red
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'Can quyen Administrator. Chuot phai PowerShell -> Run as administrator.' -ForegroundColor Red
    exit 1
}

$content = @(Get-Content -LiteralPath $hostsPath -Encoding UTF8)
$removed = @($content | Where-Object { $_ -match '(?i)justplay\.synology\.me' })
if ($removed.Count -lt 1) {
    Write-Host 'Khong co dong justplay.synology.me trong hosts — khong can sua.' -ForegroundColor Green
    exit 0
}

Write-Host "Se xoa $($removed.Count) dong:" -ForegroundColor Yellow
$removed | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }

$filtered = @($content | Where-Object { $_ -notmatch '(?i)justplay\.synology\.me' })
Set-Content -LiteralPath $hostsPath -Value $filtered -Encoding ASCII

ipconfig /flushdns | Out-Null

Write-Host ''
Write-Host 'Da xoa xong. Kiem tra:' -ForegroundColor Green
Write-Host '  nslookup justplay.synology.me  -> nen ra 14.161.25.119'
Write-Host ''
Write-Host 'Test WebDAV (thay MAT_KHAU Portal):'
Write-Host "  curl.exe -sk -u 'lvanhthu:MAT_KHAU' -X PROPFIND -H `"Depth: 0`" `"https://justplay.synology.me:5678/05_MARKETING/`" -w `"`nHTTP:%{http_code}`n`""
Write-Host '  -> can HTTP:207 truoc khi cau hinh RaiDrive'
