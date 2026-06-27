# JustPlay NAS - Khoi dong ket noi WebDAV
# Neu Windows chan file .bat:
#   Chuot phai file nay -> Run with PowerShell
# Hoac mo PowerShell va chay:
#   powershell -ExecutionPolicy Bypass -File ".\Chay-Ket-Noi-NAS.ps1"

$ErrorActionPreference = 'Stop'

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
        'JustPlay-NAS-Config.json'
    )
    foreach ($name in $names) {
        $src = Join-Path $SourceDir $name
        $dst = Join-Path $WorkDir $name
        if (-not (Test-Path -LiteralPath $src)) {
            if ($name -eq 'JustPlay-NAS-Config.json') { continue }
            throw "Thieu file $name trong thu muc cai dat. Giai nen day du file ZIP."
        }
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }
    Get-ChildItem -LiteralPath $WorkDir -File -ErrorAction SilentlyContinue |
        Unblock-File -ErrorAction SilentlyContinue
}

$sourceDir = $PSScriptRoot
if (-not $sourceDir) {
    $sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

Get-ChildItem -LiteralPath $sourceDir -File -ErrorAction SilentlyContinue |
    Unblock-File -ErrorAction SilentlyContinue

$workDir = Get-NasBundleWorkDir
Sync-NasBundleToWorkDir -SourceDir $sourceDir -WorkDir $workDir

$prep = Join-Path $workDir 'Prepare-JustPlay-WebClient.ps1'
$main = Join-Path $workDir 'JustPlay-NAS-RaiDrive-Setup.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $prep
if ($LASTEXITCODE -ne 0) {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [System.Windows.Forms.MessageBox]::Show(
            "Khong cau hinh duoc WebClient.`nChap nhan UAC khi duoc hoi va chay lai.",
            'JustPlay NAS',
            'OK',
            'Warning'
        ) | Out-Null
    } catch {
        Write-Host 'Khong cau hinh duoc WebClient. Chap nhan UAC khi duoc hoi va chay lai.'
        Read-Host 'Nhan Enter de dong'
    }
    exit $LASTEXITCODE
}

$argLine = "powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File `"$main`""
Start-Process -FilePath 'explorer.exe' -ArgumentList $argLine | Out-Null
exit 0
