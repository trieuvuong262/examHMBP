# Cấu hình RustDesk client Windows trỏ server nội bộ JustPlay.
# Chạy PowerShell (Admin) trên máy nhân viên / IT:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\rustdesk-configure-client-windows.ps1 -ServerHost rd.justplay.vn -PublicKey "PASTE_KEY"

param(
    [Parameter(Mandatory = $true)]
    [string] $ServerHost,

    [Parameter(Mandatory = $true)]
    [string] $PublicKey,

    [string] $ConfigDir = "$env:APPDATA\RustDesk\config"
)

$ErrorActionPreference = 'Stop'

$tomlPath = Join-Path $ConfigDir 'RustDesk2.toml'
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$key = $PublicKey.Trim()

$content = @"
[options]
custom-rendezvous-server = '$ServerHost'
relay-server = '$ServerHost'
api-server = ''
key = '$key'
"@

Set-Content -Path $tomlPath -Value $content -Encoding UTF8

Write-Host "Đã ghi: $tomlPath"
Write-Host "Khởi động lại RustDesk (thoát icon tray rồi mở lại)."
Write-Host ""
Write-Host "Trên client: Network -> Unlock -> kiểm tra ID/Relay = $ServerHost và Key khớp."
