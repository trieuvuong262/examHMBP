# Gỡ chặn Windows (Mark of the Web) và mở Ket-Noi-NAS-JustPlay.exe
# Nếu double-click .ps1 bị chặn: chuột phải -> Run with PowerShell
# Hoặc chạy Chay-Ket-Noi-NAS.bat

$ErrorActionPreference = 'Stop'

$dir = $PSScriptRoot
if (-not $dir) {
    $dir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

$exe = Join-Path $dir 'Ket-Noi-NAS-JustPlay.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host 'Thieu Ket-Noi-NAS-JustPlay.exe. Giai nen day du file ZIP.' -ForegroundColor Red
    Read-Host 'Nhan Enter de dong'
    exit 1
}

try {
    Unblock-File -LiteralPath $exe -ErrorAction SilentlyContinue
} catch {}

Start-Process -FilePath $exe -WorkingDirectory $dir
exit 0
