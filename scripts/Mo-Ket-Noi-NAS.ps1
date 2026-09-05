# Gỡ chặn Windows và mở JustPlay Công cụ IT (EXE — chỉ Windows)
# Chạy: double-click Chay-Ket-Noi-NAS.bat

$ErrorActionPreference = 'Stop'

function Remove-MarkOfTheWeb {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    try { Unblock-File -LiteralPath $Path -ErrorAction SilentlyContinue } catch {}
    try {
        $stream = "${Path}:Zone.Identifier"
        if (Test-Path -LiteralPath $stream) {
            Remove-Item -LiteralPath $stream -Force -ErrorAction Stop
        }
    } catch {}
}

function Clear-BundleMotw {
    param([string]$Dir)
    Get-ChildItem -LiteralPath $Dir -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-MarkOfTheWeb -Path $_.FullName
    }
}

function Start-JustPlayNasExe {
    param(
        [string]$Dir,
        [string]$ExePath
    )
    $proc = Start-Process -FilePath $ExePath -WorkingDirectory $Dir -PassThru
    Start-Sleep -Milliseconds 1200
    if (-not $proc.HasExited) { return $true }
    return $false
}

$dir = $PSScriptRoot
if (-not $dir) {
    $dir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Clear-BundleMotw -Dir $dir

$exe = Join-Path $dir 'Ket-Noi-NAS-JustPlay.exe'
$hasRustdesk = Test-Path -LiteralPath (Join-Path $dir 'JustPlay-RustDesk-Setup.ps1')
$hasEquipment = Test-Path -LiteralPath (Join-Path $dir 'JustPlay-Equipment-Scan.ps1')

if (-not $hasRustdesk -and -not $hasEquipment) {
    Write-Host 'Thieu script Windows trong ZIP. Tai lai JustPlay-Cong-Cu-IT-Windows.zip tu Portal.' -ForegroundColor Red
    Read-Host 'Nhan Enter de dong'
    exit 1
}

if (Test-Path -LiteralPath $exe) {
    Remove-MarkOfTheWeb -Path $exe
    try {
        if (Start-JustPlayNasExe -Dir $dir -ExePath $exe) { exit 0 }
    } catch {
        Write-Host "EXE bi chan: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host 'Khong mo duoc Ket-Noi-NAS-JustPlay.exe.' -ForegroundColor Red
if ($hasRustdesk) { Write-Host '  - JustPlay-RustDesk-Setup.ps1' }
if ($hasEquipment) { Write-Host '  - JustPlay-Equipment-Scan.ps1' }
Read-Host 'Nhan Enter de dong'
exit 1
