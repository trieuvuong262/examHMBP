# Chay NAS WebDAV truc tiep tu repo - khong can ZIP / deploy VPS.
# Can quyen Admin khi -Connect hoac -Gui (WebClient registry).
#
# Vi du:
#   .\Run-NAS-Local-Connect.ps1 -ListOnly
#   .\Run-NAS-Local-Connect.ps1 -Gui
#   .\Run-NAS-Local-Connect.ps1 -Connect -Username huuchung
#   python scripts/export_nas_local_config.py huuchung

#Requires -Version 5.1
param(
    [string]$Username = '',
    [string]$Password = '',
    [switch]$Connect,
    [switch]$ListOnly,
    [switch]$Gui,
    [switch]$Validate
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainPs1 = Join-Path $ScriptDir 'JustPlay-NAS-RaiDrive-Setup.ps1'

function Write-Usage {
    Write-Host @"

JustPlay NAS - local dev (tu repo, khong ZIP)

  Run-NAS-Local-Connect.bat                 Form GUI (Admin)
  .\Run-NAS-Local-Connect.ps1 -ListOnly     Ke hoach o dia Z..V
  .\Run-NAS-Local-Connect.ps1 -Connect      Map WebDAV (Admin)
  .\Run-NAS-Local-Connect.ps1 -Validate     Chay test_nas_ps1_validate.ps1

Config: scripts/JustPlay-NAS-Config.local.json (gitignore)
        hoac: python scripts/export_nas_local_config.py <username>

Mat khau: nhap khi -Connect, hoac dat `$env:JUSTPLAY_NAS_PASSWORD (khong log).

"@ -ForegroundColor Cyan
}

if ($Validate) {
    & (Join-Path $ScriptDir 'test_nas_ps1_validate.ps1')
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $MainPs1)) {
    throw "Thieu file $MainPs1"
}

$env:JUSTPLAY_NAS_LOCAL_DEV = '1'
. $MainPs1

if ($ListOnly) {
    if (-not (Test-JustPlayNasBundleReady)) {
        Write-Host 'Chua co config local.' -ForegroundColor Yellow
        Write-Host 'Copy JustPlay-NAS-Config.local.json.example -> JustPlay-NAS-Config.local.json'
        Write-Host 'Hoac: python scripts/export_nas_local_config.py <username>'
        exit 2
    }
    Write-Host "Script: $NasScriptVersion"
    Write-Host "Server: ${Server}:${WebDavPort} (LDAP @$LdapDomain)"
    Write-Host "User hint: $PortalUsernameHint"
    Write-Host "Shares: $(Get-NasShareNamesLabel)"
    Write-Host ''
    Write-Host 'Drive plan:'
    Get-NasShareDriveAssignments | Format-Table ShareName, Letter -AutoSize
    exit 0
}

if ($Gui) {
    if (-not (Test-JustPlayNasBundleReady)) {
        Show-JustPlayNasBundleError
        exit 2
    }
    Show-JustPlayNasDialog
    exit 0
}

if ($Connect) {
    if (-not (Test-JustPlayNasBundleReady)) {
        throw 'Chua co JustPlay-NAS-Config.local.json - xem -ListOnly help.'
    }
    if (-not $Username) {
        $Username = [string]$PortalUsernameHint
    }
    if (-not $Username) {
        throw 'Can -Username hoac portal_username trong config local.'
    }
    if (-not $Password) {
        $Password = [string]$env:JUSTPLAY_NAS_PASSWORD
    }
    if (-not $Password) {
        $sec = Read-Host 'Mat khau Portal (LDAP)' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try {
            $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }

    Write-Host "[JustPlay] Map WebDAV cho $Username - $(Format-NasDriveAssignmentsLabel)"
    $result = Connect-AllJustPlayNasShares -Username $Username -Password $Password
    foreach ($m in $result.Mapped) {
        Write-Host "OK $($m.Letter): $($m.ShareName) -> $($m.RemotePath)" -ForegroundColor Green
    }
    if ($result.Errors -and $result.Errors.Count -gt 0) {
        Write-Host 'Canh bao (share khac van OK):' -ForegroundColor Yellow
        $result.Errors | ForEach-Object { Write-Host "  $_" }
    }
    Write-Host "WinUser: $($result.WinUser)"
    exit 0
}

Write-Usage
exit 0
