# JustPlay - tu dong gan o NAS qua WebDAV (cong 5678). Chi WebDAV, khong SMB.
# User/pass = tai khoan Portal (LDAP). Khong can cau hinh RaiDrive thu cong.
#
# Chay: double-click JustPlay-NAS-RaiDrive-Setup.bat

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:Ps1Path = $MyInvocation.MyCommand.Path

$Server = '__NAS_SERVER__'
$PortRaw = '__NAS_PORT__'
$WebDavPortRaw = '__NAS_WEBDAV_PORT__'
$SmbPortRaw = '__NAS_SMB_PORT__'
$NasFallbackServer = '__NAS_FALLBACK_SERVER__'
$LdapDomain = '__NAS_LDAP_DOMAIN__'
$PortalPasswordUrl = '__PORTAL_PASSWORD_URL__'
$PortalUsernameHint = '__PORTAL_USERNAME__'
$NasSharesCsv = '__NAS_SHARES__'
$NasPrimaryShare = '__NAS_PRIMARY_SHARE__'
$DeptFolderCode = '__NAS_DEPT_CODE__'
$DriveLetterRaw = '__NAS_DRIVE_LETTER__'
$BlockedDefaultPassword = 'justplay@123'
$NasScriptVersion = '2026.06.27.21'

$Script:NasWebDavShareAliases = @{
    'KD-MKT' = '05_MARKETING'
}

function Get-ShareNameList {
    param([object]$Raw)
    if ($null -eq $Raw) { return @() }
    if ($Raw -is [string]) {
        return @(
            $Raw -split ',' |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
        )
    }
    return @(
        @($Raw) |
        ForEach-Object { [string]$_ } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
    )
}

function Read-InlineNasShares {
    if (-not $NasSharesCsv -or $NasSharesCsv -match '^__.+__$') { return @() }
    return Get-ShareNameList $NasSharesCsv
}

function Read-TextFileAutoEncoding {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        return [System.Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        return [System.Text.Encoding]::BigEndianUnicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return [System.Text.Encoding]::UTF8.GetString($bytes, 3, $bytes.Length - 3)
    }
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Import-JustPlayNasConfigFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $raw = Read-TextFileAutoEncoding -Path $Path
        return (ConvertFrom-Json -InputObject $raw)
    } catch {
        return $null
    }
}

function Import-JustPlayNasConfig {
    $merged = $null
    $fileNames = New-Object System.Collections.Generic.List[string]
    [void]$fileNames.Add('JustPlay-NAS-Config.json')
    if ($env:JUSTPLAY_NAS_LOCAL_DEV -eq '1') {
        [void]$fileNames.Add('JustPlay-NAS-Config.local.json')
    }
    foreach ($fileName in $fileNames) {
        $cfg = Import-JustPlayNasConfigFile (Join-Path $ScriptDir $fileName)
        if (-not $cfg) { continue }
        if (-not $merged) {
            $merged = $cfg
            continue
        }
        foreach ($prop in $cfg.PSObject.Properties) {
            $merged | Add-Member -NotePropertyName $prop.Name -NotePropertyValue $prop.Value -Force
        }
    }
    return $merged
}

function Merge-ShareNameLists {
    param([object[]]$Lists)
    $merged = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($list in $Lists) {
        if (-not $list) { continue }
        foreach ($name in $list) {
            $n = [string]$name
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$merged.Add($n)
        }
    }
    $arr = [string[]]$merged.ToArray()
    return ,$arr
}

function Import-NasShareListFromMerge {
    param([object[]]$Lists)
    $list = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($rawList in $Lists) {
        if (-not $rawList) { continue }
        foreach ($name in (Get-ShareNameList $rawList)) {
            $n = [string]$name
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$list.Add($n)
        }
    }
    return ,$list
}

$inlineShares = Read-InlineNasShares
$jsonConfig = Import-JustPlayNasConfig
if ($jsonConfig) {
    if ($jsonConfig.server) { $Server = [string]$jsonConfig.server }
    if ($null -ne $jsonConfig.port) { $PortRaw = [string]$jsonConfig.port }
    if ($null -ne $jsonConfig.webdav_port) { $WebDavPortRaw = [string]$jsonConfig.webdav_port }
    if ($null -ne $jsonConfig.smb_port) { $SmbPortRaw = [string]$jsonConfig.smb_port }
    if ($jsonConfig.fallback_server) { $NasFallbackServer = [string]$jsonConfig.fallback_server }
    if ($jsonConfig.ldap_domain) { $LdapDomain = [string]$jsonConfig.ldap_domain }
    if ($jsonConfig.portal_password_url) { $PortalPasswordUrl = [string]$jsonConfig.portal_password_url }
    if ($jsonConfig.portal_username) { $PortalUsernameHint = [string]$jsonConfig.portal_username }
    if ($null -ne $jsonConfig.dept_folder_code) { $DeptFolderCode = [string]$jsonConfig.dept_folder_code }
    if ($jsonConfig.drive_letter) { $DriveLetterRaw = [string]$jsonConfig.drive_letter }
    if ($jsonConfig.primary_share) { $NasPrimaryShare = [string]$jsonConfig.primary_share }
    if ($jsonConfig.webdav_share_aliases) {
        foreach ($prop in $jsonConfig.webdav_share_aliases.PSObject.Properties) {
            $Script:NasWebDavShareAliases[$prop.Name] = [string]$prop.Value
        }
    }
    $jsonShares = Get-ShareNameList $jsonConfig.shares
} else {
    $jsonShares = @()
}

$shareList = Import-NasShareListFromMerge @($jsonShares, $inlineShares)
if ($shareList.Count -gt 0) {
    $NasSharesCsv = ($shareList.ToArray() -join ',')
    if (-not $NasPrimaryShare -or $NasPrimaryShare -match '^__.+__$') {
        $NasPrimaryShare = $shareList.Item(0)
    }
}

if ($Server -eq '__NAS_SERVER__') { $Server = 'justplay.synology.me' }
if ($NasFallbackServer -eq '__NAS_FALLBACK_SERVER__' -or -not $NasFallbackServer) {
    $NasFallbackServer = '100.93.5.42'
}
if ($WebDavPortRaw -eq '__NAS_WEBDAV_PORT__') {
    if ($PortRaw -ne '__NAS_PORT__') { $WebDavPort = [int]$PortRaw } else { $WebDavPort = 5678 }
} else {
    $WebDavPort = [int]$WebDavPortRaw
}
if ($SmbPortRaw -eq '__NAS_SMB_PORT__') { $SmbPort = 445 } else { $SmbPort = [int]$SmbPortRaw }
if ($LdapDomain -eq '__NAS_LDAP_DOMAIN__') { $LdapDomain = 'ldap.justplay.local' }
if ($PortalPasswordUrl -eq '__PORTAL_PASSWORD_URL__') {
    $PortalPasswordUrl = 'https://portal.justplay.vn/accounts/password/change/'
}
if ($PortalUsernameHint -eq '__PORTAL_USERNAME__') { $PortalUsernameHint = '' }
if ($DeptFolderCode -eq '__NAS_DEPT_CODE__') { $DeptFolderCode = '' }
if ($DriveLetterRaw -eq '__NAS_DRIVE_LETTER__') { $DriveLetter = 'Z' } else { $DriveLetter = $DriveLetterRaw.Trim().ToUpperInvariant() }

function Resolve-WebDavShareName {
    param([string]$Name)
    $n = ([string]$Name).Trim()
    if (-not $n) { return '' }
    if ($Script:NasWebDavShareAliases.ContainsKey($n)) {
        return [string]$Script:NasWebDavShareAliases[$n]
    }
    return $n
}

function New-NasShareNameList {
    $result = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    if ($NasSharesCsv -and $NasSharesCsv -notmatch '^__.+__$') {
        foreach ($name in (Get-ShareNameList $NasSharesCsv)) {
            $n = Resolve-WebDavShareName ([string]$name)
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$result.Add($n)
        }
    }
    if ($result.Count -lt 1) {
        $merged = Import-NasShareListFromMerge @($jsonShares, $inlineShares)
        foreach ($name in $merged) {
            $n = Resolve-WebDavShareName ([string]$name)
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$result.Add($n)
        }
    }
    return ,$result
}

function Resolve-SingleNasShareName {
    param([string]$Candidate = '')
    if ($Candidate -and $Candidate -notmatch '\s' -and $Candidate -notmatch ',') {
        return (Resolve-WebDavShareName $Candidate.Trim())
    }
    if ($NasPrimaryShare -and $NasPrimaryShare -notmatch '^__.+__$') {
        return (Resolve-WebDavShareName $NasPrimaryShare.Trim())
    }
    if ($NasSharesCsv -and $NasSharesCsv -notmatch '^__.+__$') {
        $commaIdx = $NasSharesCsv.IndexOf(',')
        if ($commaIdx -gt 0) {
            return $NasSharesCsv.Substring(0, $commaIdx).Trim()
        }
        if ($NasSharesCsv -match '\s') {
            return (($NasSharesCsv -split '\s+')[0]).Trim()
        }
        return $NasSharesCsv.Trim()
    }
    $list = New-NasShareNameList
    if ($null -ne $list -and $list.Count -ge 1) {
        return $list.Item(0)
    }
    return ''
}

function Get-PrimaryNasShareName {
    return (Resolve-SingleNasShareName '')
}

function Get-NasShareNamesLabel {
    $list = New-NasShareNameList
    if ($null -eq $list -or $list.Count -lt 1) { return '' }
    return ($list.ToArray() -join ', ')
}

function Test-JustPlayNasBundleReady {
    if ((New-NasShareNameList).Count -ge 1) { return $true }
    if ($Server -match '^__.+__$') { return $false }
    if ($NasSharesCsv -match '^__.+__$') { return $false }
    return $false
}

function Show-JustPlayNasBundleError {
    Add-Type -AssemblyName System.Windows.Forms
    $configPath = Join-Path $ScriptDir 'JustPlay-NAS-Config.json'
    $hasConfig = Test-Path -LiteralPath $configPath
    $hasPlaceholder = ($Server -match '^__.+__$') -or ($NasSharesCsv -match '^__.+__$')

    if ($hasPlaceholder) {
        $localPath = Join-Path $ScriptDir 'JustPlay-NAS-Config.local.json'
        $devHint = if (Test-Path -LiteralPath $localPath) {
            ''
        } else {
            @"

Dev (test tu repo): tao scripts\JustPlay-NAS-Config.local.json
hoac chay: python scripts/export_nas_local_config.py <username>
roi: scripts\Run-NAS-Local-Connect.bat
"@
        }
        $msg = @"
Bo cai chua duoc dong goi tu Portal (file .ps1 van con __NAS_...__).

Vui long tai lai ZIP tu Thu vien -> Tai NAS (Ctrl+F5), giai nen va chay .bat trong thu muc do.$devHint
"@
    } elseif (-not $hasConfig) {
        $msg = @"
Thieu file JustPlay-NAS-Config.json trong thu muc cai dat.

Giai nen DAY DU file ZIP (4 file) roi chay JustPlay-NAS-RaiDrive-Setup.bat.
"@
    } else {
        $msg = @"
Tai khoan chua duoc gan share NAS tren Portal (danh sach share trong ZIP rong).

Lien he IT de gan phong ban hoac thu muc NAS, sau do tai lai ZIP.
"@
    }
    [System.Windows.Forms.MessageBox]::Show($msg, 'JustPlay NAS', 'OK', 'Error') | Out-Null
}

function Write-Log([string]$Message) {
    Write-Host "[JustPlay] $Message"
}

$NasConnectTimeoutSec = 25
$NasPortCheckTimeoutMs = 10000

function Get-NasServerCandidates {
    $merged = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($hostName in @($Server, $NasFallbackServer)) {
        $n = [string]$hostName
        if (-not $n -or $seen.ContainsKey($n)) { continue }
        $seen[$n] = $true
        [void]$merged.Add($n)
    }
    return @($merged.ToArray())
}

function Test-NasServerPort {
    param(
        [string]$HostName,
        [int]$NasPort,
        [int]$TimeoutMs = $NasPortCheckTimeoutMs
    )
    $targets = New-Object System.Collections.Generic.List[string]
    try {
        foreach ($addr in [System.Net.Dns]::GetHostAddresses($HostName)) {
            if ($addr.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
                [void]$targets.Add($addr.ToString())
            }
        }
    } catch {}
    if ($targets.Count -lt 1) {
        [void]$targets.Add($HostName)
    }

    foreach ($target in $targets) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $connect = $client.BeginConnect($target, $NasPort, $null, $null)
            if (-not $connect.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
                continue
            }
            $client.EndConnect($connect)
            return $HostName
        } catch {
            continue
        } finally {
            $client.Close()
        }
    }
    throw "Khong mo duoc cong $NasPort toi $HostName (timeout ${TimeoutMs}ms)."
}

function Set-WebClientAuthForwardHost {
    param(
        [string]$HostName,
        [int]$DavPort = 0
    )
    $hostName = [string]$HostName
    if (-not $hostName) { return $false }
    $basicPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters'
    if (-not (Test-Path -LiteralPath $basicPath)) { return $false }
    $changed = $false
    try {
        $toAdd = @($hostName)
        if ($DavPort -gt 0) {
            $toAdd += "${hostName}:${DavPort}"
            $toAdd += "https://${hostName}:${DavPort}"
            $toAdd += "https://${hostName}"
        }
        $cur = (Get-ItemProperty -Path $basicPath -Name AuthForwardServerList -ErrorAction SilentlyContinue).AuthForwardServerList
        $entries = New-Object System.Collections.Generic.List[string]
        foreach ($e in (Expand-AuthForwardList $cur)) {
            [void]$entries.Add($e)
        }
        foreach ($item in $toAdd) {
            if ($entries -notcontains $item) {
                [void]$entries.Add($item)
                $changed = $true
            }
        }
        if ($changed) {
            Set-ItemProperty -Path $basicPath -Name AuthForwardServerList -Value $entries.ToArray() `
                -Type MultiString -ErrorAction Stop
        }
        $curBasic = Get-ItemProperty -Path $basicPath -Name BasicAuthLevel -ErrorAction SilentlyContinue
        if ($null -eq $curBasic -or [int]$curBasic.BasicAuthLevel -lt 2) {
            Set-ItemProperty -Path $basicPath -Name BasicAuthLevel -Value 2 -ErrorAction Stop
            $changed = $true
        }
        $useBasic = Get-ItemProperty -Path $basicPath -Name UseBasicAuth -ErrorAction SilentlyContinue
        if ($null -eq $useBasic -or [int]$useBasic.UseBasicAuth -ne 1) {
            Set-ItemProperty -Path $basicPath -Name UseBasicAuth -Value 1 -Type DWord -ErrorAction SilentlyContinue
            $changed = $true
        }
    } catch {
        return $false
    }
    return $changed
}

function Expand-AuthForwardList {
    param($Raw)
    $list = New-Object System.Collections.Generic.List[string]
    if (-not $Raw) { return ,$list.ToArray() }
    foreach ($item in @($Raw)) {
        foreach ($part in ([string]$item -split "`r?`n")) {
            $p = $part.Trim()
            if ($p) { [void]$list.Add($p) }
        }
    }
    return ,$list.ToArray()
}

function Test-IsAdministrator {
    return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WebClientAuthForwardEntries {
    param([string]$HostName, [int]$DavPort)
    $entries = New-Object System.Collections.Generic.List[string]
    foreach ($h in @($HostName, $Server, $NasFallbackServer)) {
        $n = [string]$h
        if (-not $n) { continue }
        [void]$entries.Add($n)
        if ($DavPort -gt 0) {
            [void]$entries.Add("${n}:${DavPort}")
            [void]$entries.Add("https://${n}:${DavPort}")
            [void]$entries.Add("https://${n}")
        }
    }
    return ,$entries.ToArray()
}

function Test-WebClientRegistryReady {
    param(
        [string]$HostName,
        [int]$DavPort
    )
    $basicPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters'
    if (-not (Test-Path -LiteralPath $basicPath)) { return $false }
    try {
        $b = Get-ItemProperty -Path $basicPath
        if ($null -eq $b.BasicAuthLevel -or [int]$b.BasicAuthLevel -lt 2) { return $false }
        if ($null -ne $b.UseBasicAuth -and [int]$b.UseBasicAuth -ne 1) { return $false }
        $cur = $b.AuthForwardServerList
        $list = New-Object System.Collections.Generic.List[string]
        foreach ($e in (Expand-AuthForwardList $cur)) {
            [void]$list.Add($e)
        }
        foreach ($need in (Get-WebClientAuthForwardEntries -HostName $HostName -DavPort $DavPort)) {
            if ($list -notcontains $need) { return $false }
        }
        $svc = Get-Service WebClient -ErrorAction SilentlyContinue
        if (-not $svc -or $svc.Status -ne 'Running') { return $false }
        return $true
    } catch {
        return $false
    }
}

function Invoke-JustPlayWebClientPrep {
    param(
        [string]$HostName,
        [int]$DavPort
    )
    if (Test-WebClientRegistryReady -HostName $HostName -DavPort $DavPort) { return }
    $prepScript = Join-Path $ScriptDir 'Prepare-JustPlay-WebClient.ps1'
    if (-not (Test-Path -LiteralPath $prepScript)) {
        throw "Thieu file $prepScript"
    }
    if (Test-IsAdministrator) {
        Ensure-WebClientReady -HostName $HostName -DavPort $DavPort
    } else {
        $argList = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$prepScript`"",
            '-HostName', $HostName, '-DavPort', [string]$DavPort
        )
        $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $argList
        if ($proc.ExitCode -ne 0) {
            throw 'Khong cau hinh duoc WebClient (UAC bi huy hoac loi Admin).'
        }
    }
    if (-not (Test-WebClientRegistryReady -HostName $HostName -DavPort $DavPort)) {
        throw 'WebClient chua san sang sau khi chay Admin. Thu lai Run-NAS-Local-Connect.bat.'
    }
}

function Ensure-WebClientReady {
    param(
        [string]$HostName,
        [int]$DavPort
    )
    $svc = Get-Service WebClient -ErrorAction SilentlyContinue
    if (-not $svc) {
        throw 'Khong tim thay dich vu WebClient tren Windows.'
    }
    if ($svc.Status -ne 'Running') {
        try {
            Set-Service WebClient -StartupType Manual -ErrorAction SilentlyContinue
            Start-Service WebClient -ErrorAction Stop
        } catch {
            throw 'Dich vu WebClient chua chay. Mo services.msc -> WebClient -> Start (can quyen Admin).'
        }
    }
    $registryChanged = $false
    foreach ($h in @($HostName, $Server, $NasFallbackServer)) {
        if ($h) {
            $registryChanged = (Set-WebClientAuthForwardHost -HostName $h -DavPort $DavPort) -or $registryChanged
        }
    }
    if ($registryChanged) {
        try {
            Restart-Service WebClient -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        } catch {
            Write-Log 'Khong restart duoc WebClient - chay .bat bang quyen Administrator.'
        }
    }
}

function Get-NasPortalLoginNames {
    param([string]$Username)
    $logins = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($n in @($PortalUsernameHint, $Username)) {
        $n = ([string]$n).Trim()
        if (-not $n -or $seen.ContainsKey($n)) { continue }
        $seen[$n] = $true
        [void]$logins.Add($n)
    }
    return ,$logins.ToArray()
}

function Get-NasWebDavWinUsers {
    param([string]$Username)
    $formats = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($login in (Get-NasPortalLoginNames $Username)) {
        foreach ($fmt in @(
            "$login@$LdapDomain",
            "$LdapDomain\$login",
            $login
        )) {
            if ($seen.ContainsKey($fmt)) { continue }
            $seen[$fmt] = $true
            [void]$formats.Add($fmt)
        }
    }
    return ,$formats.ToArray()
}

function Initialize-NasWNetApi {
    if ($script:NasWNetApiReady) { return }
    $source = @'
using System;
using System.Runtime.InteropServices;

public class NasWNet {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public class NETRESOURCE {
        public int dwScope = 0;
        public int dwType = 1;
        public int dwDisplayType = 0;
        public int dwUsage = 0;
        public string lpLocalName = null;
        public string lpRemoteName = null;
        public string lpComment = null;
        public string lpProvider = null;
    }

    [DllImport("mpr.dll", CharSet = CharSet.Unicode)]
    public static extern int WNetAddConnection2(NETRESOURCE lpNetResource, string lpPassword, string lpUsername, int dwFlags);

    [DllImport("mpr.dll", CharSet = CharSet.Unicode)]
    public static extern int WNetCancelConnection2(string lpName, int dwFlags, bool fForce);
}
'@
    Add-Type -TypeDefinition $source -ErrorAction Stop
    $script:NasWNetApiReady = $true
}

function Get-WNetErrorMessage {
    param([int]$Code)
    switch ($Code) {
        1244 { return 'System error 1244 - user has not been authenticated (thu user dang UPN: Ten@ldap.justplay.local, dung hoa thuong Portal)' }
        1326 { return 'System error 1326 - sai mat khau hoac user' }
        1219 { return 'System error 1219 - da co ket noi WebDAV khac; thu ngat ket noi cu' }
        default { return "WNetAddConnection2 error $Code" }
    }
}

function Get-NasShareDriveLetterPool {
    return @('Z', 'Y', 'X', 'W', 'V', 'U', 'T', 'S', 'R', 'Q', 'P', 'O', 'N', 'M', 'L', 'K', 'J', 'I', 'H', 'G', 'F', 'E', 'D', 'C')
}

function Get-NasShareDriveAssignments {
    $shares = New-NasShareNameList
    if ($null -eq $shares -or $shares.Count -lt 1) {
        return @()
    }
    $pool = Get-NasShareDriveLetterPool
    $start = 0
    if ($DriveLetter) {
        $idx = [array]::IndexOf($pool, $DriveLetter)
        if ($idx -ge 0) { $start = $idx }
    }
    $result = New-Object System.Collections.Generic.List[object]
    for ($i = 0; $i -lt $shares.Count; $i++) {
        if (($start + $i) -ge $pool.Count) { break }
        $name = Resolve-SingleNasShareName ([string]$shares.Item($i))
        if (-not $name) { continue }
        [void]$result.Add([pscustomobject]@{
            ShareName = $name
            Letter    = $pool[$start + $i]
        })
    }
    return ,$result.ToArray()
}

function Format-NasDriveAssignmentsLabel {
    $assignments = Get-NasShareDriveAssignments
    if ($null -eq $assignments -or $assignments.Count -lt 1) { return '' }
    return (($assignments | ForEach-Object { "$($_.Letter): $($_.ShareName)" }) -join ', ')
}

function Clear-NasWebDavHostConnections {
    param(
        [string]$HostName,
        [int]$DavPort,
        [string]$Letter = ''
    )
    if ($Letter) {
        Remove-NasDriveMap -Letter $Letter
    }
}

function Invoke-NasWebDavPsDriveMap {
    param(
        [string]$Letter,
        [string]$RemoteSpec,
        [string]$WinUser,
        [string]$PlainPassword
    )
    if (-not (Get-Command New-PSDrive -ErrorAction SilentlyContinue)) {
        throw 'New-PSDrive khong co'
    }
    if (Get-PSDrive -Name $Letter -ErrorAction SilentlyContinue) {
        Remove-PSDrive -Name $Letter -Force -ErrorAction SilentlyContinue
    }
    $secure = ConvertTo-SecureString $PlainPassword -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($WinUser, $secure)
    $null = New-PSDrive -Name $Letter -PSProvider FileSystem -Root $RemoteSpec `
        -Credential $cred -Persist -Scope Global -ErrorAction Stop
    if (-not (Test-Path "${Letter}:\")) {
        throw 'PSDrive map xong nhung khong doc duoc o dia'
    }
}

function Invoke-NasWebDavWNetMap {
    param(
        [string]$Letter,
        [string]$RemoteSpec,
        [string]$WinUser,
        [string]$PlainPassword
    )
    Initialize-NasWNetApi
    $localPath = "${Letter}:"
    [void][NasWNet]::WNetCancelConnection2($localPath, 0, $true)
    $nr = New-Object NasWNet+NETRESOURCE
    $nr.lpLocalName = $localPath
    $nr.lpRemoteName = $RemoteSpec
    foreach ($flags in @(0x4, 0x1)) {
        $rc = [NasWNet]::WNetAddConnection2($nr, $PlainPassword, $WinUser, $flags)
        if ($rc -eq 0) { return }
    }
    throw (Get-WNetErrorMessage $rc)
}

function Resolve-NasWebDavWinUser {
    param(
        [string]$HostName,
        [int]$DavPort,
        [string]$ShareName,
        [string]$Username,
        [string]$PlainPassword
    )
    foreach ($winUser in (Get-NasWebDavWinUsers $Username)) {
        try {
            $authOk = Test-NasWebDavAuth -HostName $HostName -DavPort $DavPort -ShareName $ShareName `
                -WinUser $winUser -PlainPassword $PlainPassword
            if ($authOk -eq $true) {
                return $winUser
            }
        } catch {
            continue
        }
    }
    return $null
}

function Test-NasWebDavAuth {
    param(
        [string]$HostName,
        [int]$DavPort,
        [string]$ShareName,
        [string]$WinUser,
        [string]$PlainPassword
    )
    if (-not $HostName) { throw 'Thieu hostname WebDAV.' }
    $url = Get-WebDavShareUrl -HostName $HostName -DavPort $DavPort -ShareName $ShareName
    $prevCb = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.Method = 'HEAD'
        $req.Timeout = 8000
        $req.Credentials = New-Object System.Net.NetworkCredential($WinUser, $PlainPassword)
        $req.PreAuthenticate = $true
        try {
            $resp = $req.GetResponse()
            $code = [int]$resp.StatusCode
            $resp.Close()
            return ($code -ge 200 -and $code -lt 400)
        } catch [System.Net.WebException] {
            $resp = $_.Exception.Response
            if (-not $resp) { throw $_.Exception.Message }
            $code = [int]$resp.StatusCode
            $resp.Close()
            if ($code -eq 401) { return $false }
            if ($code -eq 404) { throw "Share khong ton tai tren WebDAV: $ShareName" }
            if ($code -eq 403) {
                return $true
            }
            return ($code -ge 200 -and $code -lt 400)
        }
    } finally {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $prevCb
    }
}

function Test-NasWebDavTlsTrust {
    param(
        [string]$HostName,
        [int]$DavPort
    )
    if (-not $HostName) { return $true }
    $tcp = $null
    $ssl = $null
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect($HostName, $DavPort)
        $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false)
        $ssl.AuthenticateAsClient($HostName)
        return $true
    } catch {
        $certHint = ''
        try {
            if ($ssl -and $ssl.RemoteCertificate) {
                $c = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
                $certHint = " (cert CN=$($c.GetNameInfo('SimpleName', $false)))"
            }
        } catch {}
        throw @"
Windows khong tin chung chi SSL cua NAS cho hostname $HostName`:$DavPort$certHint.
WebClient se bao loi 1244 du user/pass dung.

IT: DSM -> Control Panel -> Security -> Certificate -> cap Let's Encrypt cho $HostName (hoac import cert dung ten mien).
Sau khi sua cert, chay lai Run-NAS-Local-Connect.bat (Admin).
"@
    } finally {
        if ($ssl) { $ssl.Close() }
        if ($tcp) { $tcp.Close() }
    }
}

function Get-WebDavShareUrl {
    param(
        [string]$HostName,
        [int]$DavPort,
        [string]$ShareName
    )
    $pathShare = ($ShareName -replace ' ', '%20')
    return "https://${HostName}:${DavPort}/${pathShare}/"
}

function Get-WebDavUncPath {
    param(
        [string]$HostName,
        [int]$DavPort,
        [string]$ShareName
    )
    return "\\${HostName}@SSL@${DavPort}\DavWWWRoot\${ShareName}"
}

function Invoke-NasWebDavNetUse {
    param(
        [string]$Letter,
        [string]$RemoteSpec,
        [string]$WinUser,
        [string]$PlainPassword,
        [string]$Label,
        [int]$TimeoutSec = $NasConnectTimeoutSec
    )
    $localPath = "${Letter}:"
    if (Test-Path $localPath) {
        & net use $localPath /delete /y 2>$null | Out-Null
    }
    $null = Invoke-ProcessWithTimeout -FilePath 'net.exe' `
        -ArgumentList (Format-NetUseArgumentString -LocalPath $localPath -RemotePath $RemoteSpec `
            -WinUser $WinUser -PlainPassword $PlainPassword) `
        -TimeoutSec $TimeoutSec -Label $Label
}

function Invoke-NasWebDavMapTimed {
    param(
        [string]$Letter,
        [string]$HostName,
        [int]$DavPort,
        [string]$ShareName,
        [string]$WinUser,
        [string]$PlainPassword,
        [switch]$SkipCredentialPrep,
        [int]$TimeoutSec = $NasConnectTimeoutSec
    )
    if (-not $SkipCredentialPrep) {
        Invoke-JustPlayWebClientPrep -HostName $HostName -DavPort $DavPort
        Save-WebDavCredentials -HostName $HostName -DavPort $DavPort -WinUser $WinUser -PlainPassword $PlainPassword
    }
    Clear-NasWebDavHostConnections -HostName $HostName -DavPort $DavPort -Letter $Letter
    $davUrl = Get-WebDavShareUrl -HostName $HostName -DavPort $DavPort -ShareName $ShareName
    $davUnc = Get-WebDavUncPath -HostName $HostName -DavPort $DavPort -ShareName $ShareName
    $lastErr = $null
    foreach ($spec in @($davUnc, $davUrl)) {
        foreach ($mapFn in @(
            { param($s) Invoke-NasWebDavPsDriveMap -Letter $Letter -RemoteSpec $s -WinUser $WinUser -PlainPassword $PlainPassword },
            { param($s) Invoke-NasWebDavWNetMap -Letter $Letter -RemoteSpec $s -WinUser $WinUser -PlainPassword $PlainPassword },
            { param($s) Invoke-NasWebDavNetUse -Letter $Letter -RemoteSpec $s -WinUser $WinUser -PlainPassword $PlainPassword -Label "WebDAV $s" }
        )) {
            try {
                & $mapFn $spec
                return $spec
            } catch {
                $lastErr = $_.Exception.Message
                if (-not $lastErr) { $lastErr = [string]$_ }
            }
        }
    }
    throw $lastErr
}

function Resolve-NasConnectPlans {
    $plans = New-Object System.Collections.Generic.List[object]
    $failures = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in (Get-NasServerCandidates)) {
        $hostLabel = [string]$candidate
        if (-not $hostLabel) { continue }
        try {
            $null = Test-NasServerPort -HostName $hostLabel -NasPort $WebDavPort
            [void]$plans.Add([pscustomobject]@{
                Host = $hostLabel
                ConnectHost = $hostLabel
                Protocol = 'webdav'
                Port = [int]$WebDavPort
            })
        } catch {
            [void]$failures.Add("WebDAV ${hostLabel}:${WebDavPort} - $($_.Exception.Message)")
        }
    }
    if ($plans.Count -lt 1) {
        $shareHint = Get-PrimaryNasShareName
        if (-not $shareHint) { $shareHint = 'TEN_SHARE' }
        throw @"
Khong ket noi duoc NAS.
$($failures -join "`n")

Thu WebDAV: https://${Server}:${WebDavPort}/${shareHint}
"@
    }
    return ,$plans
}

function Invoke-ProcessWithTimeout {
    param(
        [string]$FilePath,
        [string]$ArgumentList,
        [int]$TimeoutSec = $NasConnectTimeoutSec,
        [string]$Label = 'process'
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $ArgumentList
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill() } catch {}
        throw "${Label} timeout (${TimeoutSec}s)"
    }
    $output = ($proc.StandardOutput.ReadToEnd() + $proc.StandardError.ReadToEnd()).Trim()
    if ($proc.ExitCode -ne 0) {
        if ($output) { throw $output }
        throw "${Label} failed (exit $($proc.ExitCode))"
    }
    return $output
}

function Quote-NetArg {
    param([string]$Value)
    if ($null -eq $Value) { return '""' }
    return '"' + ($Value.Replace('"', '""')) + '"'
}

function Format-NetUseArgumentString {
    param(
        [string]$LocalPath,
        [string]$RemotePath,
        [string]$WinUser,
        [string]$PlainPassword,
        [switch]$WebDavOrder,
        [int]$TcpPort = 0
    )
    $parts = @('use', $LocalPath, (Quote-NetArg $RemotePath))
    if ($WebDavOrder) {
        $parts += (Quote-NetArg $PlainPassword)
        $parts += "/user:$(Quote-NetArg $WinUser)"
    } else {
        $parts += "/user:$(Quote-NetArg $WinUser)"
        $parts += (Quote-NetArg $PlainPassword)
    }
    $parts += '/persistent:yes'
    if ($TcpPort -gt 0) { $parts += "/TCPPORT:$TcpPort" }
    return ($parts -join ' ')
}

function Format-NetArguments {
    param([string[]]$Args)
    ($Args | ForEach-Object {
        if ($_ -match '[\s@:/\\"''^&|<>]') { Quote-NetArg $_ } else { $_ }
    }) -join ' '
}

function Get-JobFailureMessage {
    param($Job)
    if (-not $Job) { return 'Ket noi NAS that bai.' }
    $chunks = New-Object System.Collections.Generic.List[string]
    $reason = $Job.ChildJobs[0].JobStateInfo.Reason
    if ($reason) {
        $base = $reason
        if ($base.InnerException) { $base = $base.InnerException }
        [void]$chunks.Add([string]$base.Message)
    }
    $received = Receive-Job -Job $Job -ErrorAction SilentlyContinue 2>&1
    foreach ($item in @($received)) {
        if ($null -eq $item) { continue }
        if ($item -is [System.Management.Automation.ErrorRecord]) {
            [void]$chunks.Add([string]$item.Exception.Message)
        } else {
            $text = [string]$item
            if ($text) { [void]$chunks.Add($text) }
        }
    }
    $msg = ($chunks | Where-Object { $_ } | Select-Object -Unique) -join ' | '
    if ($msg) { return $msg }
    return 'Ket noi NAS that bai.'
}

function Remove-NasDriveMap {
    param([string]$Letter)
    $localPath = "${Letter}:"
    if (Test-Path $localPath) {
        & net use $localPath /delete /y 2>$null | Out-Null
    }
}

function Save-WebDavCredentials {
    param(
        [string]$HostName,
        [int]$DavPort,
        [string]$WinUser,
        [string]$PlainPassword
    )
    $userArg = Quote-NetArg $WinUser
    $passArg = Quote-NetArg $PlainPassword
    $targets = @(
        "https://${HostName}:${DavPort}",
        "https://${HostName}",
        "${HostName}:${DavPort}",
        $HostName
    )
    foreach ($target in $targets) {
        $targetArg = Quote-NetArg $target
        & cmdkey /delete:$target 2>$null | Out-Null
        & cmdkey /delete:"MicrosoftOffice16_Data:$target" 2>$null | Out-Null
        $null = & cmdkey /generic:$targetArg /user:$userArg /pass:$passArg 2>&1
        if ($LASTEXITCODE -ne 0) {
            $null = & cmdkey /add:$targetArg /user:$userArg /pass:$passArg 2>&1
        }
    }
}

function Save-NasCredential {
    param([string]$Target, [string]$WinUser, [string]$PlainPassword)
    $targetArg = Quote-NetArg $Target
    $userArg = Quote-NetArg $WinUser
    $passArg = Quote-NetArg $PlainPassword
    & cmdkey /delete:$Target 2>$null | Out-Null
    $null = & cmdkey /generic:$targetArg /user:$userArg /pass:$passArg 2>&1
    if ($LASTEXITCODE -ne 0) {
        $null = & cmdkey /add:$targetArg /user:$userArg /pass:$passArg
    }
}

function Invoke-NasNetUseTimed {
    param(
        [string]$Letter,
        [string]$RemotePath,
        [string]$WinUser,
        [string]$PlainPassword,
        [switch]$UseTcpPort,
        [int]$NasPort,
        [int]$TimeoutSec = $NasConnectTimeoutSec
    )
    $label = if ($UseTcpPort) { "net use /TCPPORT:$NasPort" } else { 'net use' }
    $localPath = "${Letter}:"
    if (Test-Path $localPath) {
        & net use $localPath /delete /y 2>$null | Out-Null
    }
    $argStr = Format-NetUseArgumentString -LocalPath $localPath -RemotePath $RemotePath `
        -WinUser $WinUser -PlainPassword $PlainPassword
    if ($UseTcpPort) { $argStr += " /TCPPORT:$NasPort" }
    $null = Invoke-ProcessWithTimeout -FilePath 'net.exe' `
        -ArgumentList $argStr `
        -TimeoutSec $TimeoutSec -Label $label
}

function Invoke-NasSmbMappingTimed {
    param(
        [string]$Letter,
        [string]$RemotePath,
        [string]$WinUser,
        [string]$PlainPassword,
        [int]$NasPort,
        [int]$TimeoutSec = $NasConnectTimeoutSec
    )
    if (-not (Get-Command New-SmbMapping -ErrorAction SilentlyContinue)) {
        throw 'New-SmbMapping khong co (can Windows 10/11 ban moi)'
    }
    $secure = ConvertTo-SecureString $PlainPassword -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($WinUser, $secure)
    if ($NasPort -eq 445) {
        New-SmbMapping -LocalPath "${Letter}:" -RemotePath $RemotePath `
            -Credential $cred -Persistent $true -ErrorAction Stop | Out-Null
    } else {
        New-SmbMapping -LocalPath "${Letter}:" -RemotePath $RemotePath -TcpPort ([uint16]$NasPort) `
            -Credential $cred -Persistent $true -ErrorAction Stop | Out-Null
    }
}

function Invoke-NasNetUse {
    param(
        [string]$Letter,
        [string]$RemotePath,
        [string]$WinUser,
        [string]$PlainPassword,
        [switch]$UseTcpPort
    )
    Invoke-NasNetUseTimed -Letter $Letter -RemotePath $RemotePath -WinUser $WinUser `
        -PlainPassword $PlainPassword -UseTcpPort:$UseTcpPort -NasPort $SmbPort
}

function Invoke-NasSmbMapping {
    param(
        [string]$Letter,
        [string]$RemotePath,
        [string]$WinUser,
        [securestring]$SecurePassword
    )
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    Invoke-NasSmbMappingTimed -Letter $Letter -RemotePath $RemotePath -WinUser $WinUser `
        -PlainPassword $plain -NasPort $SmbPort
}

function Connect-AllJustPlayNasShares {
    param(
        [string]$Username,
        [string]$Password
    )
    $assignments = Get-NasShareDriveAssignments
    if ($null -eq $assignments -or $assignments.Count -lt 1) {
        throw @"
Chua co share NAS trong bo cai.
1) Vao Portal -> Thu vien -> Tai NAS -> tai lai ZIP moi
2) Dam bao tai khoan da gan phong ban hoac thu muc NAS (IT)
Neu van loi, lien he IT.
"@
    }

    $planBag = Resolve-NasConnectPlans
    $tlsHost = [string]$planBag[0].ConnectHost
    $tlsPort = [int]$planBag[0].Port
    if ($tlsHost) {
        Test-NasWebDavTlsTrust -HostName $tlsHost -DavPort $tlsPort | Out-Null
    }
    $errors = New-Object System.Collections.Generic.List[string]
    $mapped = New-Object System.Collections.Generic.List[object]
    $winUser = $null
    $prepHost = $null
    $prepPort = 0
    $credentialSaved = $false

    foreach ($item in $assignments) {
        $shareName = [string]$item.ShareName
        $letter = [string]$item.Letter
        Remove-NasDriveMap -Letter $letter
        $shareConnected = $false

        foreach ($plan in $planBag) {
            if (-not $plan -or -not $plan.ConnectHost) { continue }
            $resolvedServer = [string]$plan.ConnectHost
            $connectPort = [int]$plan.Port

            if (-not $winUser) {
                $winUser = Resolve-NasWebDavWinUser -HostName $resolvedServer -DavPort $connectPort `
                    -ShareName $shareName -Username $Username -PlainPassword $Password
                if (-not $winUser) {
                    [void]$errors.Add("Share ${shareName}: mat khau sai hoac share khong ton tai tren WebDAV")
                    break
                }
            } else {
                $authOk = $null
                try {
                    $authOk = Test-NasWebDavAuth -HostName $resolvedServer -DavPort $connectPort `
                        -ShareName $shareName -WinUser $winUser -PlainPassword $Password
                } catch {
                    $authOk = $null
                }
                if ($authOk -eq $false) {
                    [void]$errors.Add("Share ${shareName}: khong co quyen WebDAV voi user $winUser")
                    break
                }
            }

            if (-not $credentialSaved) {
                Invoke-JustPlayWebClientPrep -HostName $resolvedServer -DavPort $connectPort
                Save-WebDavCredentials -HostName $resolvedServer -DavPort $connectPort `
                    -WinUser $winUser -PlainPassword $Password
                $prepHost = $resolvedServer
                $prepPort = $connectPort
                $credentialSaved = $true
            }

            $davTarget = "https://${resolvedServer}:${connectPort}/${shareName}/"
            try {
                $davUrl = Invoke-NasWebDavMapTimed -Letter $letter -HostName $resolvedServer `
                    -DavPort $connectPort -ShareName $shareName -WinUser $winUser `
                    -PlainPassword $Password -SkipCredentialPrep
                [void]$mapped.Add([pscustomobject]@{
                    Letter     = $letter
                    ShareName  = $shareName
                    RemotePath = $davUrl
                    Method     = "WebDAV ($resolvedServer`:$connectPort)"
                })
                $shareConnected = $true
                break
            } catch {
                $msg = $_.Exception.Message
                if (-not $msg) { $msg = [string]$_ }
                [void]$errors.Add("Share ${shareName} (${letter}:): WebDAV $davTarget ($winUser): $msg")
            }
        }

        if (-not $shareConnected -and -not $winUser) {
            break
        }
    }

    if ($mapped.Count -lt 1) {
        $shareLabel = (Format-NasDriveAssignmentsLabel)
    if (-not $shareLabel) {
        $shareLabel = (($assignments | ForEach-Object { $_.ShareName }) -join ', ')
    }
        $loginHint = if ($winUser) { $winUser } else { "$Username@$LdapDomain" }
        throw (@"
Khong ket noi duoc NAS (WebDAV).
Shares da thu: $shareLabel
User Portal: $Username
$($errors -join "`n")

Goi y:
- Dung user dang UPN: $loginHint
- Mat khau = mat khau Portal; doi mat khau Portal de dong bo LDAP NAS
- URL: https://${Server}:${WebDavPort}/<share>
- Chay .bat bang quyen Administrator
"@
        )
    }

    return @{
        Mapped  = $mapped.ToArray()
        WinUser = $winUser
        Errors  = @($errors | Where-Object { $_ })
        PrepHost = $prepHost
        PrepPort = $prepPort
    }
}

function Connect-JustPlayNasShare {
    param(
        [string]$Username,
        [string]$Password,
        [string]$ShareName,
        [string]$Letter
    )
    $result = Connect-AllJustPlayNasShares -Username $Username -Password $Password
    $first = $result.Mapped | Select-Object -First 1
    if (-not $first) {
        throw 'Khong co share NAS nao duoc gan.'
    }
    return @{
        Letter     = $first.Letter
        RemotePath = $first.RemotePath
        WinUser    = $result.WinUser
        ShareName  = $first.ShareName
        Method     = $first.Method
        Mapped     = $result.Mapped
        Errors     = $result.Errors
    }
}

function Open-NasExplorerForMappedShares {
    param([object[]]$Mapped)
    if ($Mapped -and $Mapped.Count -gt 0) {
        Start-Process explorer.exe 'shell:MyComputerFolder'
        return 'May tinh (cac o NAS da gan)'
    }
    Start-Process explorer.exe 'shell:MyComputerFolder'
    return 'May tinh'
}

function Open-NasExplorerPath {
    param([string]$Letter, [string]$Username)
    $openPath = "${Letter}:\"
    Start-Process explorer.exe $openPath
    return $openPath
}

function Show-JustPlayNasDialog {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $jpRed = [System.Drawing.Color]::FromArgb(220, 38, 38)
    $jpRedDark = [System.Drawing.Color]::FromArgb(185, 28, 28)
    $jpBg = [System.Drawing.Color]::FromArgb(248, 250, 252)
    $jpCard = [System.Drawing.Color]::White
    $jpMuted = [System.Drawing.Color]::FromArgb(100, 116, 139)
    $jpText = [System.Drawing.Color]::FromArgb(15, 23, 42)
    $fontUi = New-Object System.Drawing.Font('Segoe UI', 10)
    $fontTitle = New-Object System.Drawing.Font('Segoe UI', 15, [System.Drawing.FontStyle]::Bold)
    $fontSub = New-Object System.Drawing.Font('Segoe UI', 9.5)
    $fontLabel = New-Object System.Drawing.Font('Segoe UI', 9, [System.Drawing.FontStyle]::Bold)

    $primaryShare = Get-PrimaryNasShareName
    $allSharesLabel = Get-NasShareNamesLabel
    $drivePlanLabel = Format-NasDriveAssignmentsLabel
    $shareLabel = if ($primaryShare) { $primaryShare } else { 'NAS' }
    $assignments = Get-NasShareDriveAssignments
    $driveCount = if ($assignments) { $assignments.Count } else { 0 }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'JustPlay NAS'
    $form.Font = $fontUi
    $form.ClientSize = New-Object System.Drawing.Size(440, 520)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.BackColor = $jpBg
    $form.ForeColor = $jpText

    $header = New-Object System.Windows.Forms.Panel
    $header.Dock = 'Top'
    $header.Height = 96
    $header.BackColor = $jpRed
    $form.Controls.Add($header)

    $lblBrand = New-Object System.Windows.Forms.Label
    $lblBrand.Text = 'JustPlay NAS'
    $lblBrand.Font = $fontTitle
    $lblBrand.ForeColor = [System.Drawing.Color]::White
    $lblBrand.AutoSize = $true
    $lblBrand.Location = New-Object System.Drawing.Point(28, 22)
    $header.Controls.Add($lblBrand)

    $lblSub = New-Object System.Windows.Forms.Label
    $lblSub.Text = if ($drivePlanLabel) {
        "Gan $driveCount o dia: $drivePlanLabel | $NasScriptVersion"
    } elseif ($primaryShare) {
        "Chua gan duoc ke hoach o dia - tai lai ZIP [$NasScriptVersion]"
    } else {
        "Chua co share trong ZIP - tai lai tu Portal (Thu vien -> Tai NAS) [$NasScriptVersion]"
    }
    $lblSub.Font = $fontSub
    $lblSub.ForeColor = [System.Drawing.Color]::FromArgb(254, 226, 226)
    $lblSub.AutoSize = $true
    $lblSub.Location = New-Object System.Drawing.Point(30, 56)
    $header.Controls.Add($lblSub)

    $card = New-Object System.Windows.Forms.Panel
    $card.Location = New-Object System.Drawing.Point(24, 112)
    $card.Size = New-Object System.Drawing.Size(392, 188)
    $card.BackColor = $jpCard
    $card.BorderStyle = 'FixedSingle'
    $form.Controls.Add($card)

    $lblUser = New-Object System.Windows.Forms.Label
    $lblUser.Text = 'Ten dang nhap Portal'
    $lblUser.Font = $fontLabel
    $lblUser.ForeColor = $jpMuted
    $lblUser.AutoSize = $true
    $lblUser.Location = New-Object System.Drawing.Point(20, 20)
    $card.Controls.Add($lblUser)

    $tbUser = New-Object System.Windows.Forms.TextBox
    $tbUser.Font = New-Object System.Drawing.Font('Segoe UI', 11)
    $tbUser.Location = New-Object System.Drawing.Point(20, 44)
    $tbUser.Size = New-Object System.Drawing.Size(220, 28)
    $tbUser.BorderStyle = 'FixedSingle'
    if ($PortalUsernameHint) { $tbUser.Text = $PortalUsernameHint }
    $card.Controls.Add($tbUser)

    $lblSuffix = New-Object System.Windows.Forms.Label
    $lblSuffix.Text = "@$LdapDomain"
    $lblSuffix.Font = New-Object System.Drawing.Font('Segoe UI', 9.5)
    $lblSuffix.ForeColor = $jpMuted
    $lblSuffix.AutoSize = $true
    $lblSuffix.Location = New-Object System.Drawing.Point(248, 48)
    $card.Controls.Add($lblSuffix)

    $lblPass = New-Object System.Windows.Forms.Label
    $lblPass.Text = 'Mat khau Portal'
    $lblPass.Font = $fontLabel
    $lblPass.ForeColor = $jpMuted
    $lblPass.AutoSize = $true
    $lblPass.Location = New-Object System.Drawing.Point(20, 88)
    $card.Controls.Add($lblPass)

    $tbPass = New-Object System.Windows.Forms.TextBox
    $tbPass.Font = New-Object System.Drawing.Font('Segoe UI', 11)
    $tbPass.Location = New-Object System.Drawing.Point(20, 112)
    $tbPass.Size = New-Object System.Drawing.Size(352, 28)
    $tbPass.UseSystemPasswordChar = $true
    $tbPass.BorderStyle = 'FixedSingle'
    $card.Controls.Add($tbPass)

    $lblHint = New-Object System.Windows.Forms.Label
    $lblHint.Text = if ($driveCount -gt 1) {
        "WebDAV cong $WebDavPort - gan $driveCount share (moi share mot o dia), mo May tinh sau khi dang nhap."
    } else {
        "WebDAV cong $WebDavPort - gan share NAS thanh o dia, mo May tinh sau khi dang nhap."
    }
    $lblHint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
    $lblHint.ForeColor = $jpMuted
    $lblHint.AutoSize = $false
    $lblHint.Size = New-Object System.Drawing.Size(352, 32)
    $lblHint.Location = New-Object System.Drawing.Point(20, 148)
    $card.Controls.Add($lblHint)

    $logPanel = New-Object System.Windows.Forms.Panel
    $logPanel.Location = New-Object System.Drawing.Point(24, 310)
    $logPanel.Size = New-Object System.Drawing.Size(392, 132)
    $logPanel.BackColor = [System.Drawing.Color]::FromArgb(254, 242, 242)
    $logPanel.BorderStyle = 'FixedSingle'
    $form.Controls.Add($logPanel)

    $lblLogTitle = New-Object System.Windows.Forms.Label
    $lblLogTitle.Text = 'Nhat ky / Loi (chon Ctrl+A de copy)'
    $lblLogTitle.Font = $fontLabel
    $lblLogTitle.ForeColor = $jpMuted
    $lblLogTitle.AutoSize = $true
    $lblLogTitle.Location = New-Object System.Drawing.Point(10, 8)
    $logPanel.Controls.Add($lblLogTitle)

    $tbLog = New-Object System.Windows.Forms.TextBox
    $tbLog.Font = New-Object System.Drawing.Font('Consolas', 9)
    $tbLog.Location = New-Object System.Drawing.Point(10, 30)
    $tbLog.Size = New-Object System.Drawing.Size(292, 88)
    $tbLog.Multiline = $true
    $tbLog.ReadOnly = $true
    $tbLog.ScrollBars = 'Vertical'
    $tbLog.WordWrap = $true
    $tbLog.BorderStyle = 'FixedSingle'
    $tbLog.BackColor = [System.Drawing.Color]::White
    $tbLog.ForeColor = $jpRed
    $tbLog.TabStop = $true
    $logPanel.Controls.Add($tbLog)

    $btnCopyLog = New-Object System.Windows.Forms.Button
    $btnCopyLog.Text = 'Sao chep'
    $btnCopyLog.Font = New-Object System.Drawing.Font('Segoe UI', 9)
    $btnCopyLog.FlatStyle = 'Flat'
    $btnCopyLog.FlatAppearance.BorderColor = $jpRed
    $btnCopyLog.ForeColor = $jpRed
    $btnCopyLog.BackColor = [System.Drawing.Color]::White
    $btnCopyLog.Size = New-Object System.Drawing.Size(76, 32)
    $btnCopyLog.Location = New-Object System.Drawing.Point(306, 30)
    $btnCopyLog.Enabled = $false
    $btnCopyLog.Cursor = [System.Windows.Forms.Cursors]::Hand
    $logPanel.Controls.Add($btnCopyLog)

    $btnCopyAll = New-Object System.Windows.Forms.Button
    $btnCopyAll.Text = 'Chon het'
    $btnCopyAll.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
    $btnCopyAll.FlatStyle = 'Flat'
    $btnCopyAll.FlatAppearance.BorderColor = $jpMuted
    $btnCopyAll.ForeColor = $jpMuted
    $btnCopyAll.BackColor = [System.Drawing.Color]::White
    $btnCopyAll.Size = New-Object System.Drawing.Size(76, 28)
    $btnCopyAll.Location = New-Object System.Drawing.Point(306, 68)
    $btnCopyAll.Enabled = $false
    $btnCopyAll.Cursor = [System.Windows.Forms.Cursors]::Hand
    $logPanel.Controls.Add($btnCopyAll)

    $btnConnect = New-Object System.Windows.Forms.Button
    $btnConnect.Text = if ($driveCount -gt 1) {
        "Ket noi NAS ($driveCount o dia)"
    } else {
        "Ket noi NAS"
    }
    $btnConnect.Font = New-Object System.Drawing.Font('Segoe UI', 10.5, [System.Drawing.FontStyle]::Bold)
    $btnConnect.FlatStyle = 'Flat'
    $btnConnect.FlatAppearance.BorderSize = 0
    $btnConnect.BackColor = $jpRed
    $btnConnect.ForeColor = [System.Drawing.Color]::White
    $btnConnect.Size = New-Object System.Drawing.Size(392, 44)
    $btnConnect.Location = New-Object System.Drawing.Point(24, 422)
    $btnConnect.Cursor = [System.Windows.Forms.Cursors]::Hand
    $form.Controls.Add($btnConnect)

    $btnConnect.Add_MouseEnter({ $btnConnect.BackColor = $jpRedDark })
    $btnConnect.Add_MouseLeave({ $btnConnect.BackColor = $jpRed })

    $linkChange = New-Object System.Windows.Forms.LinkLabel
    $linkChange.Text = 'Doi mat khau tai Portal'
    $linkChange.LinkColor = $jpRed
    $linkChange.ActiveLinkColor = $jpRedDark
    $linkChange.VisitedLinkColor = $jpRed
    $linkChange.AutoSize = $true
    $linkChange.Location = New-Object System.Drawing.Point(24, 474)
    $linkChange.Cursor = [System.Windows.Forms.Cursors]::Hand
    $linkChange.Add_LinkClicked({
        Start-Process $PortalPasswordUrl
    })
    $form.Controls.Add($linkChange)

    $script:connectUser = ''
    $script:connectShare = ''

    function Set-LogText {
        param(
            [string]$Text,
            [ValidateSet('info', 'error', 'ok')]
            [string]$Level = 'info'
        )
        $tbLog.Text = $Text
        switch ($Level) {
            'error' {
                $tbLog.ForeColor = $jpRed
                $logPanel.BackColor = [System.Drawing.Color]::FromArgb(254, 242, 242)
            }
            'ok' {
                $tbLog.ForeColor = [System.Drawing.Color]::FromArgb(22, 101, 52)
                $logPanel.BackColor = [System.Drawing.Color]::FromArgb(240, 253, 244)
            }
            default {
                $tbLog.ForeColor = $jpMuted
                $logPanel.BackColor = [System.Drawing.Color]::FromArgb(248, 250, 252)
            }
        }
        $hasText = [bool]$Text
        $btnCopyLog.Enabled = $hasText
        $btnCopyAll.Enabled = $hasText
        [System.Windows.Forms.Application]::DoEvents()
    }

    function Set-Status([string]$Text) {
        Set-LogText -Text $Text -Level error
    }

    function Copy-LogToClipboard {
        param([switch]$SelectAll)
        $text = $tbLog.Text
        if (-not $text) { return }
        if ($SelectAll) {
            $tbLog.Focus() | Out-Null
            $tbLog.SelectAll()
        }
        try {
            [System.Windows.Forms.Clipboard]::SetText($text)
            $btnCopyLog.Text = 'Da copy!'
        } catch {
            $tbLog.Focus() | Out-Null
            $tbLog.SelectAll()
            Set-LogText -Text ($text + "`n`n[Clipboard bi chan - bam vao o loi, Ctrl+A, Ctrl+C]") -Level error
        }
    }

    $btnCopyLog.Add_Click({ Copy-LogToClipboard })
    $btnCopyAll.Add_Click({ Copy-LogToClipboard -SelectAll })

    function Test-DefaultPasswordBlocked {
        if ($tbPass.Text -eq $BlockedDefaultPassword) {
            Set-Status 'Mat khau mac dinh khong duoc phep. Hay doi mat khau truoc.'
            $ans = [System.Windows.Forms.MessageBox]::Show(
                "Ban dang dung mat khau mac dinh ($BlockedDefaultPassword).`n`nVui long doi mat khau tai Portal, sau do chay lai script nay.`n`nMo trang doi mat khau ngay bay gio?",
                'JustPlay NAS',
                'YesNo',
                'Warning'
            )
            if ($ans -eq 'Yes') {
                Start-Process $PortalPasswordUrl
            }
            $tbPass.Clear()
            $tbPass.Focus() | Out-Null
            return $true
        }
        return $false
    }

    $btnConnect.Add_Click({
        Set-LogText '' -Level info
        $user = $tbUser.Text.Trim()
        if (-not $user) {
            Set-Status 'Vui long nhap ten dang nhap Portal.'
            $tbUser.Focus() | Out-Null
            return
        }
        if (-not $tbPass.Text) {
            Set-Status 'Vui long nhap mat khau Portal.'
            $tbPass.Focus() | Out-Null
            return
        }
        if (Test-DefaultPasswordBlocked) { return }

        $shareName = Resolve-SingleNasShareName (Get-PrimaryNasShareName)
        if (-not $shareName) {
            Set-Status 'Chua co share trong ZIP. Tai lai tu Portal (Thu vien -> Tai NAS).'
            return
        }

        $btnConnect.Enabled = $false
        $script:connectUser = $user
        $script:connectShare = $shareName
        $mapCount = (Get-NasShareDriveAssignments).Count
        Set-LogText -Text "Dang ket noi $mapCount share NAS (toi da ~$($mapCount * 60)s)..." -Level info
        [System.Windows.Forms.Application]::DoEvents()

        try {
            $result = Connect-AllJustPlayNasShares -Username $user -Password $tbPass.Text
            $opened = Open-NasExplorerForMappedShares -Mapped $result.Mapped
            $mapLines = ($result.Mapped | ForEach-Object { "$($_.Letter): -> $($_.ShareName)" }) -join "`n"
            foreach ($m in $result.Mapped) {
                Write-Log "OK: $($m.Letter): -> $($m.RemotePath) ($($m.Method))"
            }
            $warnText = ''
            if ($result.Errors -and $result.Errors.Count -gt 0) {
                $warnText = "`n`nCanh bao (mot so share khong gan duoc):`n$($result.Errors -join "`n")"
            }
            [System.Windows.Forms.MessageBox]::Show(
                "Da gan NAS thanh cong.`n`n$mapLines`n`nUser WebDAV: $($result.WinUser)`nDa mo: $opened$warnText",
                'JustPlay NAS',
                'OK',
                'Information'
            ) | Out-Null
            $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
            $form.Close()
        } catch {
            $msg = $_.Exception.Message
            if (-not $msg) { $msg = [string]$_ }
            Set-Status $msg
            $btnConnect.Enabled = $true
        }
    })

    $form.AcceptButton = $btnConnect
    $form.CancelButton = $null
    $tbUser.Add_KeyDown({
        if ($_.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
            $tbPass.Focus() | Out-Null
            $_.SuppressKeyPress = $true
        }
    })
    $tbPass.Add_KeyDown({
        if ($_.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
            $btnConnect.PerformClick()
            $_.SuppressKeyPress = $true
        }
    })

    $form.Add_Shown({
        if ($PortalUsernameHint) {
            $tbPass.Focus() | Out-Null
        } else {
            $tbUser.Focus() | Out-Null
        }
    })
    [void]$form.ShowDialog()
}

function Start-JustPlayNasMain {
    try {
        if (-not (Test-JustPlayNasBundleReady)) {
            Show-JustPlayNasBundleError
            exit 1
        }
        Show-JustPlayNasDialog
        Write-Log 'Hoan tat.'
        exit 0
    } catch {
        [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
        [System.Windows.Forms.MessageBox]::Show(
            $_.Exception.Message,
            'JustPlay NAS - loi',
            'OK',
            'Error'
        ) | Out-Null
        Write-Error $_
        exit 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    Start-JustPlayNasMain
}
