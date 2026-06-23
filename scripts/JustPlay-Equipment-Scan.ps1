$ErrorActionPreference = 'Stop'

$PortalUrl = '__PORTAL_URL__'
$ScanSecret = '__SCAN_SECRET__'
$AssignedUserText = '__ASSIGNED_USER_TEXT__'
$DepartmentText = '__DEPARTMENT_TEXT__'

if ($PortalUrl -like '*__PORTAL*') {
    $PortalUrl = 'https://portal.justplay.vn'
}
if ($ScanSecret -like '*__SCAN*') {
    Write-Host 'LOI: Chua cau hinh SCAN SECRET. Tai file tu Portal.'
    exit 1
}
if ($AssignedUserText -like '*__ASSIGNED*') { $AssignedUserText = '' }
if ($DepartmentText -like '*__DEPARTMENT*') { $DepartmentText = '' }

function Get-PrimaryMacAddress {
    $candidates = @()
    try {
        $candidates = Get-NetAdapter -ErrorAction SilentlyContinue |
            Where-Object {
                $_.MacAddress -and
                $_.MacAddress -ne '00-00-00-00-00-00' -and
                $_.InterfaceDescription -notmatch 'Virtual|Hyper-V|VMware|Loopback|TAP|VPN|Bluetooth'
            } |
            Sort-Object @{ Expression = { if ($_.Status -eq 'Up') { 0 } else { 1 } } }, InterfaceMetric
    } catch {}

    foreach ($adapter in $candidates) {
        if ($adapter.PhysicalMediaType -eq 'Unspecified' -and $adapter.InterfaceDescription -match 'Virtual') { continue }
        return ($adapter.MacAddress -replace '-', ':').ToUpper()
    }

    try {
        $wmi = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True" -ErrorAction SilentlyContinue
        foreach ($cfg in $wmi) {
            if ($cfg.MACAddress) {
                return ($cfg.MACAddress -replace '-', ':').ToUpper()
            }
        }
    } catch {}
    return $null
}

function Get-AllMacAddresses {
    $list = @()
    try {
        Get-NetAdapter -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.MacAddress) {
                $list += [PSCustomObject]@{
                    name = $_.Name
                    mac = ($_.MacAddress -replace '-', ':').ToUpper()
                    status = $_.Status
                    speed = $_.LinkSpeed
                    description = $_.InterfaceDescription
                }
            }
        }
    } catch {}
    return $list
}

function Get-InventoryPayload {
    param([string]$PrimaryMac)
    $hostname = $env:COMPUTERNAME
    $ip = ''
    try {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Select-Object -First 1 -ExpandProperty IPAddress)
    } catch {}

    $os = $null
    $cs = $null
    $bios = $null
    $cpu = $null
    try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue } catch {}
    try { $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue } catch {}
    try { $bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue } catch {}
    try { $cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1 } catch {}

    $disks = @()
    try {
        Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction SilentlyContinue | ForEach-Object {
            $sizeGb = [math]::Round($_.Size / 1GB, 1)
            $freeGb = [math]::Round($_.FreeSpace / 1GB, 1)
            $disks += "$($_.DeviceID) ${sizeGb}GB (con ${freeGb}GB)"
        }
    } catch {}

    $gpus = @()
    try {
        Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Name) { $gpus += $_.Name }
        }
    } catch {}

    $ramGb = $null
    if ($cs -and $cs.TotalPhysicalMemory) {
        $ramGb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    }

    $rustdeskId = $null
    foreach ($rdPath in @(
        "${env:ProgramFiles}\RustDesk\rustdesk.exe",
        "${env:ProgramFiles(x86)}\RustDesk\rustdesk.exe"
    )) {
        if (Test-Path -LiteralPath $rdPath) {
            try {
                $raw = cmd.exe /c "cd /d `"$(Split-Path $rdPath)`" && `"$rdPath`" --get-id 2>nul"
                if ($raw -match '(\d{6,12})') { $rustdeskId = $Matches[1]; break }
            } catch {}
        }
    }

    $license = ''
    try {
        $lic = Get-CimInstance SoftwareLicensingService -ErrorAction SilentlyContinue
        if ($lic -and $lic.OA3xOriginalProductKey) { $license = $lic.OA3xOriginalProductKey }
    } catch {}

    $loggedIn = ''
    try { $loggedIn = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName } catch {}

  $payload = [ordered]@{
        scan_secret = $ScanSecret
        mac_address = $PrimaryMac
        hostname = $hostname
        computer_name = $hostname
        ip_address = $ip
        manufacturer = if ($cs) { $cs.Manufacturer } else { '' }
        model = if ($cs) { $cs.Model } else { '' }
        model_number = if ($cs) { $cs.Model } else { '' }
        chassis_type = if ($cs) { $cs.PCSystemType } else { '' }
        serial_number = if ($bios) { $bios.SerialNumber } else { '' }
        bios_serial = if ($bios) { $bios.SerialNumber } else { '' }
        bios_version = if ($bios) { $bios.SMBIOSBIOSVersion } else { '' }
        motherboard = if ($cs) { $cs.SystemSKUNumber } else { '' }
        domain = if ($cs) { $cs.Domain } else { '' }
        os_name = if ($os) { $os.Caption } else { '' }
        os_version = if ($os) { $os.Version } else { '' }
        os_build = if ($os) { $os.BuildNumber } else { '' }
        os_arch = if ($os) { $os.OSArchitecture } else { '' }
        windows_version = if ($os) { $os.Caption } else { '' }
        windows_license = $license
        cpu = if ($cpu) { $cpu.Name } else { '' }
        cpu_cores = if ($cpu) { $cpu.NumberOfCores } else { $null }
        cpu_threads = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $null }
        ram_gb = $ramGb
        gpu = ($gpus -join '; ')
        storage = ($disks -join '; ')
        logged_in_user = $loggedIn
        rustdesk_id = $rustdeskId
        assigned_user_text = $AssignedUserText
        department_text = $DepartmentText
        platform = 'windows'
        mac_addresses = (Get-AllMacAddresses | ConvertTo-Json -Compress -Depth 4)
        network_adapters = (Get-AllMacAddresses | ForEach-Object { "$($_.name)=$($_.mac)" }) -join ', '
    }
    return $payload
}

function Invoke-PortalApi {
    param(
        [string]$Path,
        [hashtable]$Body
    )
    $uri = ($PortalUrl.TrimEnd('/')) + $Path
    $json = $Body | ConvertTo-Json -Compress -Depth 6
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    try {
        return Invoke-RestMethod -Uri $uri -Method Post -Body $json -ContentType 'application/json; charset=utf-8'
    } catch {
        $detail = $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $detail = $_.ErrorDetails.Message
        }
        throw "Portal API loi: $detail"
    }
}

Write-Host '========================================'
Write-Host ' JustPlay - Quet cau hinh may (Windows)'
Write-Host '========================================'
Write-Host ''

$mac = Get-PrimaryMacAddress
if (-not $mac) {
    Write-Host 'LOI: Khong doc duoc dia chi MAC.'
    exit 1
}
Write-Host "MAC chinh: $mac"

Write-Host '[1/3] Kiem tra MAC tren Portal...'
$check = Invoke-PortalApi -Path '/thiet-bi/api/quyet-cau-hinh/kiem-tra/' -Body @{
    scan_secret = $ScanSecret
    mac_address = $mac
}
if ($check.exists) {
    Write-Host "      Da co thiet bi: $($check.device_code) — khong gui lai."
    Write-Host '========================================'
    exit 0
}

Write-Host '[2/3] Thu thap cau hinh may...'
$payload = Get-InventoryPayload -PrimaryMac $mac
Write-Host "      Hostname: $($payload.hostname)"
Write-Host "      OS: $($payload.os_name)"

Write-Host '[3/3] Gui len Portal (Quan ly thiet bi IT)...'
$result = Invoke-PortalApi -Path '/thiet-bi/api/quyet-cau-hinh/' -Body $payload
if ($result.status -eq 'skipped') {
    Write-Host "      Bo qua: $($result.message)"
    exit 0
}
if ($result.status -ne 'success') {
    throw ($result.message | Out-String)
}

Write-Host ''
Write-Host '========================================'
Write-Host ' THANH CONG'
Write-Host " Ma thiet bi: $($result.device_code)"
Write-Host " Ten: $($result.name)"
Write-Host ' IT xem tai Quan ly thiet bi -> Danh sach IT'
Write-Host '========================================'
exit 0
