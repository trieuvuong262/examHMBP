$ErrorActionPreference = 'Stop'

# --- Cau hinh (Portal thay khi tai file; hoac sua tay khi test local) ---
$PortalUrl = '__PORTAL_URL__'
$RustDeskHost = '__RUSTDESK_HOST__'
$PublicKey = '__PUBLIC_KEY__'
$ClientPassword = '__CLIENT_PASSWORD__'
$ApproveMode = '__RUSTDESK_APPROVE_MODE__'
$EnrollSecret = '__ENROLL_SECRET__'
$InstallerUrl = '__INSTALLER_URL_WIN__'
$AssignedUserText = '__ASSIGNED_USER_TEXT__'
$DepartmentText = '__DEPARTMENT_TEXT__'

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
if ($ApproveMode -like '*__RUSTDESK*' -or -not $ApproveMode) {
    $ApproveMode = 'password'
}
if ($AssignedUserText -like '*__ASSIGNED*') {
    $AssignedUserText = ''
}
if ($DepartmentText -like '*__DEPARTMENT*') {
    $DepartmentText = ''
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-IsPhysicalLanIPv4 {
    param([string]$Ip)
    if (-not $Ip) { return $false }
    if ($Ip -like '127.*') { return $false }
    if ($Ip -like '169.254.*') { return $false }
    if ($Ip -like '192.168.65.*') { return $false }
    if ($Ip -match '^172\.(1[6-9]|2[0-9]|3[01])\.') { return $false }
    return $true
}

function Get-PrimaryLanIPv4 {
    $virtualPattern = 'Virtual|Hyper-V|VMware|Docker|WSL|TAP|VPN|Loopback|Bluetooth|Npcap|vEthernet'
    try {
        $adapters = Get-NetAdapter -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Status -eq 'Up' -and
                $_.InterfaceDescription -notmatch $virtualPattern
            } |
            Sort-Object @{ Expression = { if ($_.Physical) { 0 } else { 1 } } }, InterfaceMetric
        foreach ($adapter in $adapters) {
            $addr = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object { Test-IsPhysicalLanIPv4 $_.IPAddress } |
                Sort-Object InterfaceMetric |
                Select-Object -First 1 -ExpandProperty IPAddress
            if ($addr) { return $addr }
        }
    } catch {}
    try {
        $addr = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { Test-IsPhysicalLanIPv4 $_.IPAddress } |
            Sort-Object InterfaceMetric |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($addr) { return $addr }
    } catch {}
    return ''
}

function Get-ProperRustDeskExe {
    foreach ($p in @(
        "${env:ProgramFiles}\RustDesk\rustdesk.exe",
        "${env:ProgramFiles(x86)}\RustDesk\rustdesk.exe"
    )) {
        if (Test-Path -LiteralPath $p) {
            return (Get-Item -LiteralPath $p).FullName
        }
    }
    return $null
}

function Find-RustDeskExe {
    $proper = Get-ProperRustDeskExe
    if ($proper) { return $proper }
    $portable = "$env:LOCALAPPDATA\RustDesk\rustdesk.exe"
    if (Test-Path -LiteralPath $portable) {
        return (Get-Item -LiteralPath $portable).FullName
    }
    return $null
}

function Test-RustDeskExeWorks {
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) { return $false }
    $isProper = ($Exe -like '*\Program Files\*') -or ($Exe -like '*\Program Files (x86)\*')
    if (-not $isProper) { return $false }
    try {
        $id = Get-RustDeskIdFromCli -Exe $Exe
        if ($id) { return $true }
    } catch {}
    return $false
}

function Clear-RustDeskLeftovers {
    Write-Host '      Don dep RustDesk cu (sau go cai dat khong sach)...'
    Stop-RustDesk
    $svc = Get-Service -Name 'RustDesk' -ErrorAction SilentlyContinue
    if ($svc) {
        Stop-Service -Name 'RustDesk' -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Remove-RustDeskService
        Write-Host '      Da go service RustDesk cu.'
    }
    foreach ($dir in @(
        "$env:LOCALAPPDATA\RustDesk",
        (Join-Path $env:APPDATA 'RustDesk'),
        'C:\Windows\ServiceProfiles\LocalService\AppData\Roaming\RustDesk'
    )) {
        if (Test-Path -LiteralPath $dir) {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "      Da xoa: $dir"
        }
    }
    $startup = Join-Path ([Environment]::GetFolderPath('CommonStartup')) 'JustPlay-RustDesk.bat'
    if (Test-Path -LiteralPath $startup) {
        Remove-Item -LiteralPath $startup -Force -ErrorAction SilentlyContinue
    }
}

function Test-RustDeskServiceReady {
    $out = (& sc.exe query RustDesk 2>&1 | Out-String).Trim()
    if ($out -match '(?i)does not exist|1060|marked for deletion') { return $null }
    if ($out -match 'STATE\s*:\s*\d+\s+RUNNING') { return 'Running' }
    if ($out -match 'STATE\s*:\s*\d+\s+STOPPED') { return 'Stopped' }
    if ($out -match 'STATE\s*:\s*\d+\s+START_PENDING') { return 'Pending' }
    if ($out -match 'STATE\s*:\s*\d+\s+STOP_PENDING') { return 'Pending' }
    if ($out -match 'STATE') { return 'Unknown' }
    return $null
}

function Remove-RustDeskService {
    try {
        Stop-Service -Name 'RustDesk' -Force -ErrorAction SilentlyContinue
    } catch {}
    & sc.exe stop RustDesk 2>$null | Out-Null
    Start-Sleep -Seconds 2
    & sc.exe delete RustDesk 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

function Start-RustDeskServiceSafe {
    $state = Test-RustDeskServiceReady
    if ($state -eq 'Running') { return $true }
    if (-not $state) { return $false }
    try {
        & sc.exe start RustDesk 2>&1 | Out-Null
        for ($i = 1; $i -le 10; $i++) {
            Start-Sleep -Seconds 1
            if ((Test-RustDeskServiceReady) -eq 'Running') { return $true }
        }
    } catch {}
    return $false
}

function Invoke-RustDeskCli {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$ArgumentList = @(),
        [int]$TimeoutSec = 20
    )
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "Khong tim thay rustdesk.exe: $Exe"
    }
    $workDir = Split-Path -Parent $Exe
    $proc = Start-Process -FilePath $Exe -ArgumentList $ArgumentList `
        -WorkingDirectory $workDir -PassThru -WindowStyle Hidden
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return 124
    }
    return $proc.ExitCode
}

function Wait-RustDeskInstaller {
    param(
        [System.Diagnostics.Process]$InstallerProc,
        [int]$MaxWaitSec = 180
    )
    $installed = $null
    $steps = [Math]::Max(1, [int]($MaxWaitSec / 3))
    for ($i = 1; $i -le $steps; $i++) {
        Start-Sleep -Seconds 3
        $installed = Get-ProperRustDeskExe
        if ($installed) {
            Write-Host "      Tim thay rustdesk.exe (sau $($i * 3)s)"
            break
        }
        if ($InstallerProc.HasExited) {
            $installed = Get-ProperRustDeskExe
            if ($installed) { break }
        }
    }
    if ($InstallerProc -and -not $InstallerProc.HasExited) {
        Stop-Process -Id $InstallerProc.Id -Force -ErrorAction SilentlyContinue
    }
    Get-Process -Name 'rustdesk-setup' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    return (Get-ProperRustDeskExe)
}

function Ensure-RustDeskInstalled {
    param([string]$Url)
    $proper = Get-ProperRustDeskExe
    if ($proper -and (Test-RustDeskExeWorks -Exe $proper)) {
        Write-Host "      RustDesk da cai trong Program Files: $proper"
        return $proper
    }
    if ($proper) {
        Write-Host '      RustDesk trong Program Files nhung hong - cai lai...'
    } elseif (Find-RustDeskExe) {
        Write-Host '      Chi con file portable/config cu (da go qua Control Panel) - cai lai...'
    }
    Clear-RustDeskLeftovers
    Install-RustDesk -Url $Url
    $proper = Get-ProperRustDeskExe
    if (-not $proper) {
        throw 'Cai dat xong nhung khong tim thay rustdesk.exe trong Program Files. Chay lai script hoac cai tay tu rustdesk.com.'
    }
    Write-Host "      Da cai xong: $proper"
    return $proper
}

function Install-RustDesk {
    param([string]$Url)
    $dest = Join-Path $env:TEMP 'rustdesk-setup.exe'
    Write-Host "[1/5] Tai RustDesk..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $dest -UseBasicParsing
    Write-Host "[2/5] Cai dat (silent) - RustDesk installer hay khong tu thoat, script se doi file .exe..."
    $proc = Start-Process -FilePath $dest -ArgumentList '--silent-install' -PassThru
    $installed = Wait-RustDeskInstaller -InstallerProc $proc -MaxWaitSec 180
    if (-not $installed) {
        throw 'Cai dat timeout (3 phut) - khong tim thay rustdesk.exe trong Program Files.'
    }
    Write-Host "      Da cai: $installed"
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
    $isSystemInstall = ($Exe -like '*\Program Files\*') -or ($Exe -like '*\Program Files (x86)\*')
    if (-not $isSystemInstall) {
        Write-Host '      Bo qua install-service (RustDesk portable/user).'
        return
    }

    $state = Test-RustDeskServiceReady
    if ($state) {
        if ($state -ne 'Running') {
            if (-not (Start-RustDeskServiceSafe)) {
                Write-Host '      Service RustDesk loi (khong mo duoc) - cai lai...'
                Remove-RustDeskService
                $state = $null
            }
        }
        if ($state) {
            Write-Host '      Service RustDesk da co.'
            Ensure-RustDeskServiceAccount
            Ensure-RustDeskServiceAutoStart -Exe $Exe
            return
        }
    }

    Write-Host "      Chay: $Exe --install-service"
    $code = Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--install-service')
    if ($code -ne 0) {
        Write-Host "      Canh bao: install-service exit $code (tiep tuc user mode)."
        return
    }
    Start-Sleep -Seconds 3
    Ensure-RustDeskServiceAccount
    if (-not (Start-RustDeskServiceSafe)) {
        Write-Host '      Service chua chay - thu cai lai lan 2...'
        Remove-RustDeskService
        $code = Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--install-service')
        if ($code -eq 0) {
            Start-Sleep -Seconds 3
            Ensure-RustDeskServiceAccount
            Start-RustDeskServiceSafe | Out-Null
        }
    }
    Ensure-RustDeskServiceAutoStart -Exe $Exe
}

function Ensure-RustDeskServiceAccount {
    if (-not (Test-RustDeskServiceReady)) { return }
    try {
        Start-Process -FilePath 'sc.exe' -ArgumentList 'config', 'RustDesk', 'obj=', 'LocalSystem' `
            -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    } catch {}
}

function Ensure-RustDeskServiceAutoStart {
    param([string]$Exe)
    $state = Test-RustDeskServiceReady
    if ($state) {
        Set-Service -Name 'RustDesk' -StartupType Automatic -ErrorAction SilentlyContinue
        Start-Process -FilePath 'sc.exe' -ArgumentList 'config', 'RustDesk', 'start=', 'auto' `
            -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
        Start-Process -FilePath 'sc.exe' -ArgumentList 'failure', 'RustDesk', 'reset=', '86400', `
            'actions=', 'restart/5000/restart/5000/restart/10000' `
            -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
        if ($state -ne 'Running') {
            Start-RustDeskServiceSafe | Out-Null
        }
        Write-Host '      Windows service: Automatic + tu khoi dong khi bat may.'
        return
    }
    $isSystemInstall = ($Exe -like '*\Program Files\*') -or ($Exe -like '*\Program Files (x86)\*')
    if ($isSystemInstall) {
        Write-Host '      Canh bao: Chua co service RustDesk - chay lai script voi quyen Admin.'
    }
}

function Ensure-RustDeskStartupFolder {
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) {
        Write-Host '      Bo qua Startup: khong tim thay rustdesk.exe.'
        return
    }
    $startup = [Environment]::GetFolderPath('CommonStartup')
    if (-not $startup) {
        Write-Host '      Canh bao: Khong tim thay thu muc Windows Startup.'
        return
    }
    New-Item -ItemType Directory -Force -Path $startup | Out-Null
    $bat = Join-Path $startup 'JustPlay-RustDesk.bat'
    $hasService = [bool](Test-RustDeskServiceReady)
    if ($hasService) {
        $content = @"
@echo off
REM JustPlay - tu khoi dong RustDesk (service + tray)
sc query RustDesk | find /I "RUNNING" >nul || sc start RustDesk >nul 2>&1
timeout /t 5 /nobreak >nul
start "" "$Exe" --tray
"@
    } else {
        $content = @"
@echo off
REM JustPlay - tu khoi dong RustDesk (tray)
start "" "$Exe" --tray
"@
    }
    Set-Content -Path $bat -Value $content -Encoding ASCII
    Write-Host "      Da them vao Windows Startup (tat ca user): $bat"
}

function Show-RustDeskRemoteStatus {
    param([string]$Exe, [string]$ExpectedId)
    Write-Host '[6/6] Kiem tra san sang nhan ket noi...'
    $state = Test-RustDeskServiceReady
    if (-not $state) {
        Write-Host '      CANH BAO: Chua co Windows service - may se OFFLINE.'
        Write-Host '      Chay lai script voi quyen Administrator.'
        return
    }
    if ($state -ne 'Running') {
        Write-Host '      Service dang Stop - dang khoi dong...'
        Start-RustDeskServiceSafe | Out-Null
        Start-Sleep -Seconds 4
        $state = Test-RustDeskServiceReady
    }
    Write-Host "      Service: $state"
    Ensure-RustDeskServiceAutoStart -Exe $Exe
    Ensure-RustDeskStartupFolder -Exe $Exe
    $liveId = Get-RustDeskId -Exe $Exe
    if ($liveId -and $liveId -ne $ExpectedId) {
        Write-Host "      CANH BAO: ID hien tai ($liveId) khac ID dang ky ($ExpectedId)."
        Write-Host '      Portal can cap nhat - chay lai script hoac sua ID tren Portal.'
    }
    Write-Host ''
    Write-Host '      Luu y tren may dich:'
    Write-Host '      - Icon RustDesk mo KHONG du = phai co Service Running'
    Write-Host '      - Settings -> Network: trang thai Ready'
    Write-Host '      - KHONG bam Exit tren tray (se tat service -> Offline)'
    Write-Host "      - ID server: $RustDeskHost"
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $utf8)
}

function Get-RustDeskTomlContent {
    param([string]$HostName, [string]$Key, [switch]$WithSecurity)
    $hostOnly = ($HostName -replace ':.*$', '').Trim()
    $lines = @(
        "rendezvous_server = '${hostOnly}:21116'",
        'nat_type = 1',
        'serial = 0',
        '',
        '[options]',
        "custom-rendezvous-server = '$hostOnly'",
        "relay-server = '${hostOnly}:21117'",
        "api-server = ''",
        "key = '$Key'"
    )
    if ($WithSecurity) {
        $verify = if ($ApproveMode -eq 'click') { 'use-permanent-password' } else { 'use-permanent-password' }
        $lines += @(
            "approve-mode = '$ApproveMode'",
            "verification-method = '$verify'",
            "allow-logon-screen-password = 'Y'",
            "hide-stop-service = 'Y'"
        )
    }
    return ($lines -join "`n")
}

function Import-RustDeskConfigCli {
    param([string]$Exe, [string]$Toml)
    $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Toml))
    $code = Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--config', $b64) -TimeoutSec 15
    if ($code -eq 0 -or $code -eq 124) { return $true }
    return $false
}

function Write-RustDeskServerConfig {
    param([string]$HostName, [string]$Key, [string]$Exe)
    $toml = Get-RustDeskTomlContent -HostName $HostName -Key $Key -WithSecurity
    foreach ($dir in (Get-RustDeskConfigDirs)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $path = Join-Path $dir 'RustDesk2.toml'
        Write-Utf8NoBom -Path $path -Content $toml
        (Get-Item $path).LastWriteTime = Get-Date
        Write-Host "      Da ghi $path"
    }
    if ($Exe) {
        Write-Host '      Ap dung --config (base64)...'
        Import-RustDeskConfigCli -Exe $Exe -Toml $toml | Out-Null
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
    $state = Test-RustDeskServiceReady
    if ($state) {
        try {
            Stop-Service -Name 'RustDesk' -Force -ErrorAction SilentlyContinue
        } catch {}
        & sc.exe stop RustDesk 2>$null | Out-Null
        Start-Sleep -Seconds 2
        Start-RustDeskServiceSafe | Out-Null
        Start-Sleep -Seconds 4
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
        Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--get-id') -TimeoutSec 8 | Out-Null
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
    if (-not $Password) {
        Write-Host '      Canh bao: Chua cau hinh RUSTDESK_CLIENT_PASSWORD tren Portal.'
        return $false
    }
    $ok = $false
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        Write-Host "      Dat mat khau (lan $attempt/2)..."
        $code = Invoke-RustDeskCli -Exe $Exe -ArgumentList @('--password', $Password) -TimeoutSec 8
        if ($code -eq 0 -or $code -eq 124) {
            $ok = $true
            break
        }
        Write-Host "      Canh bao: --password exit $code"
        Start-Sleep -Seconds 2
    }
    Start-Sleep -Seconds 1
    return $ok
}

function Apply-RustDeskPassword {
    param([string]$Exe, [string]$Password)
    if (-not $Password) { return }
    Write-Host '      Khoi dong lai RustDesk service...'
    Restart-RustDesk -Exe $Exe
    [void](Set-RustDeskPassword -Exe $Exe -Password $Password)
}

function Register-PortalHost {
    param(
        [string]$PortalBase,
        [string]$Secret,
        [string]$RustDeskId,
        [string]$Password
    )
    $hostname = $env:COMPUTERNAME
    $ip = Get-PrimaryLanIPv4
    $payload = @{
        enroll_secret = $Secret
        rustdesk_id = $RustDeskId
        rustdesk_password = $Password
        hostname = $hostname
        ip_address = $ip
        name = $hostname
    }
    if ($AssignedUserText) { $payload['assigned_user_text'] = $AssignedUserText }
    if ($DepartmentText) { $payload['department_text'] = $DepartmentText }
    $payload = $payload | ConvertTo-Json -Compress
    $uri = ($PortalBase.TrimEnd('/')) + '/nhat-ky/rustdesk/api/dang-ky/'
    Write-Host "      POST $uri"
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

$exe = Ensure-RustDeskInstalled -Url $InstallerUrl
Write-Host "      Su dung: $exe"

Write-Host '[2b/5] Cai Windows service (neu chua co)...'
Install-RustDeskService -Exe $exe

Write-Host '[2c/5] Them RustDesk vao Windows Startup...'
Ensure-RustDeskStartupFolder -Exe $exe

$rdId = Get-RustDeskId -Exe $exe
if ($rdId) {
    Write-Host "      ID hien co: $rdId"
}

Write-Host "[3/5] Cau hinh server $RustDeskHost ..."
Write-RustDeskServerConfig -HostName $RustDeskHost -Key $PublicKey -Exe $exe
Restart-RustDesk -Exe $exe

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

Write-Host '[4b/5] Dat mat khau mac dinh...'
Apply-RustDeskPassword -Exe $exe -Password $ClientPassword

Write-Host '[5/5] Dang ky len Portal...'
$result = Register-PortalHost -PortalBase $PortalUrl -Secret $EnrollSecret -RustDeskId $rdId -Password $ClientPassword

Show-RustDeskRemoteStatus -Exe $exe -ExpectedId $rdId

Write-Host ''
Write-Host '========================================'
Write-Host ' THANH CONG'
Write-Host " RustDesk ID: $rdId"
Write-Host " Portal: $($result.name) (created=$($result.created))"
Write-Host " Cai dat: $exe"
Write-Host ' Kiem tra: Start Menu co RustDesk, hoac mo Programs and Features.'
Write-Host ' IT co the ket noi tai Quan tri -> RustDesk'
Write-Host '========================================'
exit 0

