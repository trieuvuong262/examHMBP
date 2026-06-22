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
        if (Test-Path -LiteralPath $p) {
            return (Get-Item -LiteralPath $p).FullName
        }
    }
    return $null
}

function Invoke-RustDeskCli {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$ArgumentList = @()
    )
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "Khong tim thay rustdesk.exe: $Exe"
    }
    $workDir = Split-Path -Parent $Exe
    $proc = Start-Process -FilePath $Exe -ArgumentList $ArgumentList `
        -WorkingDirectory $workDir -Wait -PassThru -WindowStyle Hidden
    return $proc.ExitCode
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
    $installed = Find-RustDeskExe
    if ($installed) {
        Install-RustDeskService -Exe $installed
    }
}

function Get-RustDeskConfigDirs {
    $dirs = @()
    if ($env:APPDATA) {
        $dirs += (Join-Path $env:APPDATA 'RustDesk\config')
    }
    $serviceDir = 'C:\Windows\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\config'
    if (Test-Path (Split-Path $serviceDir -Parent)) {
        $dirs += $serviceDir
    }
    return $dirs | Select-Object -Unique
}

function Install-RustDeskService {
    param([string]$Exe)
    $svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -ne 'Running') {
            Start-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
        }
        Write-Host '      Service RustDesk da co.'
        return
    }
    $isSystemInstall = ($Exe -like '*\Program Files\*') -or ($Exe -like '*\Program Files (x86)\*')
    if (-not $isSystemInstall) {
        Write-Host '      Bo qua install-service (RustDesk portable/user).'
        return
    }
    Write-Host "      Chay: $Exe --install-service"
    $code = Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--install-service')
    if ($code -ne 0) {
        Write-Host "      Canh bao: install-service exit $code (tiep tuc user mode)."
        return
    }
    Start-Sleep -Seconds 2
    $svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -ne 'Running') {
        Start-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    }
}

function Write-RustDeskServerConfig {
    param([string]$HostName, [string]$Key, [string]$Exe)
    $toml = @"
[options]
custom-rendezvous-server = '$HostName'
relay-server = '$HostName'
api-server = ''
key = '$Key'
"@
    foreach ($dir in (Get-RustDeskConfigDirs)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $path = Join-Path $dir 'RustDesk2.toml'
        Set-Content -Path $path -Value $toml -Encoding UTF8
        (Get-Item $path).LastWriteTime = Get-Date
        Write-Host "      Da ghi $path"
    }
}

function Stop-RustDesk {
    Get-Process -Name 'rustdesk','RustDesk' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

function Start-RustDesk {
    $exe = Find-RustDeskExe
    if ($exe) {
        Start-Process -FilePath $exe -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
        Start-Sleep -Seconds 6
    }
}

function Restart-RustDesk {
    param([string]$Exe)
    Stop-RustDesk
    $svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    if ($svc) {
        Restart-Service -Name 'RustDesk' -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 8
        return
    }
    Start-RustDesk
}

function Get-RustDeskIdFromCli {
    param([string]$Exe)
    try {
        $raw = cmd.exe /c "cd /d `"$(Split-Path -Parent $Exe)`" && `"$Exe`" --get-id 2>nul | more"
        $text = ($raw | Out-String).Trim()
        if ($text -match '(\d{6,12})') { return $Matches[1] }
    } catch {}

    try {
        Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--get-id') | Out-Null
        Start-Sleep -Seconds 2
        $clip = Get-Clipboard -Raw -ErrorAction SilentlyContinue
        if ($clip -and ($clip.Trim() -match '^\d{6,12}$')) {
            return $clip.Trim()
        }
    } catch {}

    return $null
}

function Get-RustDeskId {
    param([string]$Exe)
    $fromCli = Get-RustDeskIdFromCli -Exe $Exe
    if ($fromCli) { return $fromCli }

    foreach ($dir in (Get-RustDeskConfigDirs)) {
        $paths = @(
            (Join-Path $dir 'RustDesk.toml'),
            (Join-Path $dir 'RustDesk2.toml')
        )
        foreach ($path in $paths) {
            if (-not (Test-Path $path)) { continue }
            $text = Get-Content -Path $path -Raw -ErrorAction SilentlyContinue
            if ($text -match "id\s*=\s*'(\d+)'") { return $Matches[1] }
            if ($text -match 'id\s*=\s*"(\d+)"') { return $Matches[1] }
        }
    }
    return $null
}

function Set-RustDeskPassword {
    param([string]$Exe, [string]$Password)
    if (-not $Password) { return }
    Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--password', $Password) | Out-Null
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
Write-Host ' JustPlay - Cai dat RustDesk'
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
Write-Host "      Su dung: $exe"

Write-Host '[2b/5] Cai Windows service (neu chua co)...'
Install-RustDeskService -Exe $exe
Start-RustDesk

$rdId = Get-RustDeskId -Exe $exe
if ($rdId) {
    Write-Host "      ID hien co: $rdId"
}

Write-Host "[3/5] Cau hinh server $RustDeskHost ..."
Write-RustDeskServerConfig -HostName $RustDeskHost -Key $PublicKey -Exe $exe
Restart-RustDesk -Exe $exe
Set-RustDeskPassword -Exe $exe -Password $ClientPassword

Write-Host '[4/5] Doc RustDesk ID...'
if (-not $rdId) {
    for ($i = 0; $i -lt 20; $i++) {
        $rdId = Get-RustDeskId -Exe $exe
        if ($rdId) { break }
        Write-Host "      Cho RustDesk khoi tao ID... ($($i + 1)/20)"
        Start-Sleep -Seconds 5
        if ($i % 4 -eq 3) {
            Restart-RustDesk -Exe $exe
        }
    }
}
if (-not $rdId) {
    throw "Khong doc duoc RustDesk ID. Kiem tra RustDesk dang chay, ket noi $RustDeskHost, roi chay lai script."
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
