# Gỡ chặn Windows và mở JustPlay NAS (EXE hoặc PowerShell GUI nếu SmartScreen chặn EXE)
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

function Get-NasBundleWorkDir {
    return Join-Path $env:LOCALAPPDATA 'JustPlay\NAS-Setup'
}

function Sync-NasBundleToWorkDir {
    param(
        [string]$SourceDir,
        [string]$WorkDir
    )
    if (-not (Test-Path -LiteralPath $WorkDir)) {
        New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
    }
    $names = @(
        'JustPlay-NAS-RaiDrive-Setup.ps1',
        'Prepare-JustPlay-WebClient.ps1',
        'JustPlay-NAS-Config.json',
        'JustPlay-RustDesk-Setup.ps1',
        'JustPlay-Equipment-Scan.ps1'
    )
    foreach ($name in $names) {
        $src = Join-Path $SourceDir $name
        $dst = Join-Path $WorkDir $name
        if (-not (Test-Path -LiteralPath $src)) {
            if ($name -eq 'JustPlay-NAS-Config.json') { continue }
            if ($name -match '^JustPlay-(RustDesk|Equipment)') { continue }
            throw "Thieu file $name trong thu muc cai dat. Giai nen day du file ZIP."
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Remove-MarkOfTheWeb -Path $dst
    }
    Clear-BundleMotw -Dir $WorkDir
}

function Start-JustPlayNasGui {
    param([string]$WorkDir)
    $main = Join-Path $WorkDir 'JustPlay-NAS-RaiDrive-Setup.ps1'
    if (-not (Test-Path -LiteralPath $main)) {
        throw 'Thieu JustPlay-NAS-RaiDrive-Setup.ps1'
    }
    $argLine = "powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File `"$main`""
    Start-Process -FilePath 'explorer.exe' -ArgumentList $argLine | Out-Null
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
$mainPs1 = Join-Path $dir 'JustPlay-NAS-RaiDrive-Setup.ps1'

if (Test-Path -LiteralPath $exe) {
    Remove-MarkOfTheWeb -Path $exe
    try {
        if (Start-JustPlayNasExe -Dir $dir -ExePath $exe) { exit 0 }
    } catch {
        Write-Host "EXE bi chan: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if (-not (Test-Path -LiteralPath $mainPs1)) {
    Write-Host 'Thieu Ket-Noi-NAS-JustPlay.exe va script NAS. Giai nen day du file ZIP.' -ForegroundColor Red
    Read-Host 'Nhan Enter de dong'
    exit 1
}

try {
    $workDir = Get-NasBundleWorkDir
    Sync-NasBundleToWorkDir -SourceDir $dir -WorkDir $workDir
    $prep = Join-Path $workDir 'Prepare-JustPlay-WebClient.ps1'
    if (Test-Path -LiteralPath $prep) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $prep 2>$null | Out-Null
    }
    Start-JustPlayNasGui -WorkDir $workDir
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Nhan Enter de dong'
    exit 1
}
