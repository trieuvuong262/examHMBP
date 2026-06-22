$ErrorActionPreference = 'Stop'

# --- Cau hinh (Portal thay khi tai file; hoac sua tay khi test local) ---
$PortalUrl = '__PORTAL_URL__'
$RustDeskHost = '__RUSTDESK_HOST__'
$PublicKey = '__PUBLIC_KEY__'
$ClientPassword = '__CLIENT_PASSWORD__'
$EnrollSecret = '__ENROLL_SECRET__'
$InstallerUrl = '__INSTALLER_URL_WIN__'

if ($PortalUrl -like '*__PORTAL*') {
    $PortalUrl = 'https://portal.justplay.vn'
}
if ($RustDeskHost -like '*__RUSTDESK*') {
    $RustDeskHost = 'rd.justplay.vn'
}
if ($PublicKey -like '*__PUBLIC*') {
    Write-Host 'LOI: Chua cau hinh PUBLIC KEY. Tai file tu Portal hoac dien __PUBLIC_KEY__.'
    exit 1
}
if ($EnrollSecret -like '*__ENROLL*') {
    Write-Host 'LOI: Chua cau hinh ENROLL SECRET. Tai file tu Portal.'
    exit 1
}
if (-not $InstallerUrl -or $InstallerUrl -like '*__INSTALLER*') {
    $InstallerUrl = 'https://github.com/rustdesk/rustdesk/releases/download/1.3.9/rustdesk-1.3.9-x86_64.exe'
}
if ($ClientPassword -like '*__CLIENT*') {
    $ClientPassword = ''
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-RustDeskExe {
    $candidates = @(
        "${env:ProgramFiles}\RustDesk\rustdesk.exe",
        "${env:ProgramFiles(x86)}\RustDesk\rustdesk.exe",
        "$env:LOCALAPPDATA\RustDesk\rustdesk.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Install-RustDesk {
    param([string]$Url)
    $dest = Join-Path $env:TEMP 'rustdesk-setup.exe'
    Write-Host "[1/5] Tai RustDesk..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $dest -UseBasicParsing
    Write-Host "[2/5] Cai dat (silent)..."
    $proc = Start-Process -FilePath $dest -ArgumentList '--silent-install' -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Cai dat that bai (exit $($proc.ExitCode))"
    }
    Start-Sleep -Seconds 5
}

function Write-RustDeskServerConfig {
    param([string]$HostName, [string]$Key)
    $dir = Join-Path $env:APPDATA 'RustDesk\config'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $toml = @"
[options]
custom-rendezvous-server = '$HostName'
relay-server = '$HostName'
api-server = ''
key = '$Key'
"@
    $path = Join-Path $dir 'RustDesk2.toml'
    Set-Content -Path $path -Value $toml -Encoding UTF8
    Write-Host "      Da ghi $path"
}

function Stop-RustDesk {
    Get-Process -Name 'rustdesk','RustDesk' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

function Start-RustDesk {
    $exe = Find-RustDeskExe
    if ($exe) {
        Start-Process -FilePath $exe | Out-Null
        Start-Sleep -Seconds 6
    }
}

function Get-RustDeskId {
    $paths = @(
        (Join-Path $env:APPDATA 'RustDesk\config\RustDesk.toml'),
        (Join-Path $env:APPDATA 'RustDesk\config\RustDesk2.toml')
    )
    foreach ($path in $paths) {
        if (-not (Test-Path $path)) { continue }
        $text = Get-Content -Path $path -Raw -ErrorAction SilentlyContinue
        if ($text -match "id\s*=\s*'(\d+)'") { return $Matches[1] }
        if ($text -match 'id\s*=\s*"(\d+)"') { return $Matches[1] }
    }
    return $null
}

function Set-RustDeskPassword {
    param([string]$Exe, [string]$Password)
    if (-not $Password) { return }
    & $Exe --password $Password 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

function Register-PortalHost {
    param(
        [string]$PortalBase,
        [string]$Secret,
        [string]$RustDeskId,
        [string]$Password
    )
    $hostname = $env:COMPUTERNAME
    $ip = ''
    try {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Select-Object -First 1 -ExpandProperty IPAddress)
    } catch {}
    $payload = @{
        enroll_secret = $Secret
        rustdesk_id = $RustDeskId
        rustdesk_password = $Password
        hostname = $hostname
        ip_address = $ip
        name = $hostname
    } | ConvertTo-Json -Compress
    $uri = ($PortalBase.TrimEnd('/')) + '/nhat-ky/rustdesk/api/dang-ky/'
    Write-Host "[5/5] Dang ky len Portal: $uri"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $resp = Invoke-RestMethod -Uri $uri -Method Post -Body $payload -ContentType 'application/json; charset=utf-8'
    if ($resp.status -ne 'success') {
        throw ($resp.message | Out-String)
    }
    return $resp
}

Write-Host '========================================'
Write-Host ' JustPlay — Cai dat RustDesk'
Write-Host '========================================'
Write-Host ''

if (-not (Test-IsAdmin)) {
    Write-Host 'Can quyen Administrator. Chuot phai file -> Run as administrator'
    exit 1
}

$exe = Find-RustDeskExe
if (-not $exe) {
    Install-RustDesk -Url $InstallerUrl
    $exe = Find-RustDeskExe
}
if (-not $exe) {
    throw 'Khong tim thay rustdesk.exe sau khi cai.'
}

Write-Host "[3/5] Cau hinh server $RustDeskHost ..."
Stop-RustDesk
Write-RustDeskServerConfig -HostName $RustDeskHost -Key $PublicKey
Start-RustDesk
Set-RustDeskPassword -Exe $exe -Password $ClientPassword

Write-Host '[4/5] Doc RustDesk ID...'
$rdId = $null
for ($i = 0; $i -lt 12; $i++) {
    $rdId = Get-RustDeskId
    if ($rdId) { break }
    Start-Sleep -Seconds 3
    if ($i % 3 -eq 2) { Start-RustDesk }
}
if (-not $rdId) {
    throw 'Khong doc duoc RustDesk ID. Mo RustDesk, kiem tra ket noi rd.justplay.vn roi chay lai.'
}

Write-Host "      ID: $rdId"
$result = Register-PortalHost -PortalBase $PortalUrl -Secret $EnrollSecret -RustDeskId $rdId -Password $ClientPassword

Write-Host ''
Write-Host '========================================'
Write-Host ' THANH CONG'
Write-Host " RustDesk ID: $rdId"
Write-Host " Portal: $($result.name) (created=$($result.created))"
Write-Host ' IT co the ket noi tai Quan tri -> RustDesk'
Write-Host '========================================'
exit 0
