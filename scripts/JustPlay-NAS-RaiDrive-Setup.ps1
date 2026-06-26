# JustPlay - tu dong gan o NAS qua WebDAV (cong 5678). SMB 445 chi du phong trong LAN.
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
$DeptFolderCode = '__NAS_DEPT_CODE__'
$DriveLetterRaw = '__NAS_DRIVE_LETTER__'
$BlockedDefaultPassword = 'justplay@123'
$NasScriptVersion = '2026.06.25.6'

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

function Import-JustPlayNasConfig {
    $path = Join-Path $ScriptDir 'JustPlay-NAS-Config.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $raw = [System.Text.Encoding]::UTF8.GetString($bytes)
        if ($raw.StartsWith([char]0xFEFF)) {
            $raw = $raw.Substring(1)
        }
        return ($raw | ConvertFrom-Json)
    } catch {
        return $null
    }
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
    $jsonShares = Get-ShareNameList $jsonConfig.shares
} else {
    $jsonShares = @()
}

$NasShareNames = [string[]]@(Merge-ShareNameLists @($jsonShares, $inlineShares))
if ($NasShareNames.Count -gt 0) {
    $NasSharesCsv = ($NasShareNames -join ',')
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

function New-NasShareNameList {
    $result = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($item in @($NasShareNames)) {
        foreach ($name in (Get-ShareNameList $item)) {
            $n = [string]$name
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$result.Add($n)
        }
    }
    if ($result.Count -lt 1 -and $NasSharesCsv -and $NasSharesCsv -notmatch '^__.+__$') {
        foreach ($name in (Get-ShareNameList $NasSharesCsv)) {
            $n = [string]$name
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$result.Add($n)
        }
    }
    return ,$result
}

function Get-PrimaryNasShareName {
    $list = New-NasShareNameList
    if ($null -eq $list -or $list.Count -lt 1) { return '' }
    return [string]$list[0]
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
        $msg = @"
Bo cai chua duoc dong goi tu Portal (file .ps1 van con __NAS_...__).

Vui long tai lai ZIP tu Thu vien -> Tai NAS (Ctrl+F5), giai nen va chay .bat trong thu muc do.
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

function Ensure-WebClientReady {
    $svc = Get-Service WebClient -ErrorAction SilentlyContinue
    if (-not $svc) {
        throw 'Khong tim thay dich vu WebClient tren Windows.'
    }
    if ($svc.Status -ne 'Running') {
        try {
            Set-Service WebClient -StartupType Manual -ErrorAction SilentlyContinue
            Start-Service WebClient -ErrorAction Stop
        } catch {
            throw 'Dich vu WebClient chua chay. Mo services.msc -> WebClient -> Start (co the can Admin).'
        }
    }
    $basicPath = 'HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters'
    if (Test-Path -LiteralPath $basicPath) {
        try {
            $cur = Get-ItemProperty -Path $basicPath -Name BasicAuthLevel -ErrorAction SilentlyContinue
            if ($null -eq $cur -or [int]$cur.BasicAuthLevel -lt 2) {
                Set-ItemProperty -Path $basicPath -Name BasicAuthLevel -Value 2 -ErrorAction SilentlyContinue
            }
        } catch {}
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
            -WinUser $WinUser -PlainPassword $PlainPassword -WebDavOrder) `
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
        [int]$TimeoutSec = $NasConnectTimeoutSec
    )
    Ensure-WebClientReady
    $davUrl = Get-WebDavShareUrl -HostName $HostName -DavPort $DavPort -ShareName $ShareName
    $davUnc = Get-WebDavUncPath -HostName $HostName -DavPort $DavPort -ShareName $ShareName
    $lastErr = $null
    foreach ($spec in @($davUrl, $davUnc)) {
        try {
            Invoke-NasWebDavNetUse -Letter $Letter -RemoteSpec $spec -WinUser $WinUser `
                -PlainPassword $PlainPassword -Label "WebDAV $spec"
            return $spec
        } catch {
            $lastErr = $_.Exception.Message
            if (-not $lastErr) { $lastErr = [string]$_ }
        }
    }
    throw $lastErr
}

function Resolve-NasConnectPlans {
    $plans = New-Object System.Collections.Generic.List[object]
    $failures = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in (Get-NasServerCandidates)) {
        try {
            $hostReach = Test-NasServerPort -HostName $candidate -NasPort $WebDavPort
            [void]$plans.Add([pscustomobject]@{
                Host = [string]$hostReach
                ConnectHost = [string]$candidate
                Protocol = 'webdav'
                Port = [int]$WebDavPort
            })
        } catch {
            [void]$failures.Add("WebDAV ${candidate}:${WebDavPort} - $($_.Exception.Message)")
        }
    }
    if ($NasFallbackServer) {
        try {
            $hostReach = Test-NasServerPort -HostName $NasFallbackServer -NasPort $SmbPort
            [void]$plans.Add([pscustomobject]@{
                Host = [string]$hostReach
                ConnectHost = [string]$NasFallbackServer
                Protocol = 'smb'
                Port = [int]$SmbPort
            })
        } catch {
            [void]$failures.Add("SMB fallback ${NasFallbackServer}:${SmbPort} - $($_.Exception.Message)")
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
    return @($plans.ToArray())
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

function Save-NasCredential {
    param([string]$Target, [string]$WinUser, [string]$PlainPassword)
    & cmdkey /delete:$Target 2>$null | Out-Null
    $null = & cmdkey /add:$Target /user:$WinUser /pass:$PlainPassword
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

function Connect-JustPlayNasShare {
    param(
        [string]$Username,
        [string]$Password,
        [string]$ShareName,
        [string]$Letter
    )
    if (-not $ShareName) {
        throw @"
Chua co share NAS trong bo cai.
1) Vao Portal -> Thu vien -> Tai NAS -> tai lai ZIP moi
2) Dam bao tai khoan da gan phong ban hoac thu muc NAS (IT)
Neu van loi, lien he IT.
"@
    }
    $plans = Resolve-NasConnectPlans
    $winUsers = @(
        "$Username@$LdapDomain",
        "$LdapDomain\$Username",
        $Username
    )
    Remove-NasDriveMap -Letter $Letter
    $errors = New-Object System.Collections.Generic.List[string]

    foreach ($plan in $plans) {
        $resolvedServer = $plan.Host
        $connectPort = $plan.Port
        $protocol = $plan.Protocol

        foreach ($winUser in $winUsers) {
            $credTarget = if ($protocol -eq 'webdav') { $plan.ConnectHost } else { $resolvedServer }
            Save-NasCredential -Target $credTarget -WinUser $winUser -PlainPassword $Password
            if ($protocol -eq 'webdav') {
                try {
                    $davUrl = Invoke-NasWebDavMapTimed -Letter $Letter -HostName $plan.ConnectHost `
                        -DavPort $connectPort -ShareName $ShareName -WinUser $winUser -PlainPassword $Password
                    return @{
                        Letter = $Letter
                        RemotePath = $davUrl
                        WinUser = $winUser
                        Method = "WebDAV ($connectPort)"
                    }
                } catch {
                    $errors.Add("WebDAV ${plan.ConnectHost}:${connectPort} ($winUser): $($_.Exception.Message)")
                }
                continue
            }

            $remotePath = "\\$resolvedServer\$ShareName"
            $useTcpPort = ($connectPort -ne 445)
            try {
                Invoke-NasSmbMappingTimed -Letter $Letter -RemotePath $remotePath -WinUser $winUser `
                    -PlainPassword $Password -NasPort $connectPort
                return @{
                    Letter = $Letter
                    RemotePath = $remotePath
                    WinUser = $winUser
                    Method = if ($connectPort -eq 445) { 'SMB (445)' } else { "SMB ($connectPort)" }
                }
            } catch {
                $errors.Add("SMB ${resolvedServer}:${connectPort} ($winUser): $($_.Exception.Message)")
            }
            try {
                Invoke-NasNetUseTimed -Letter $Letter -RemotePath $remotePath -WinUser $winUser `
                    -PlainPassword $Password -UseTcpPort:$useTcpPort -NasPort $connectPort
                return @{
                    Letter = $Letter
                    RemotePath = $remotePath
                    WinUser = $winUser
                    Method = if ($useTcpPort) { "net use /TCPPORT:$connectPort" } else { 'net use SMB (445)' }
                }
            } catch {
                $label = if ($useTcpPort) { "net use /TCPPORT:$connectPort" } else { 'net use SMB (445)' }
                $errors.Add("${label} ${resolvedServer} ($winUser): $($_.Exception.Message)")
            }
        }
    }

    throw (@"
Khong ket noi duoc NAS.
Share: $ShareName
User: $Username
$($errors -join "`n")

Goi y: kiem tra mat khau Portal; WebDAV https://${Server}:${WebDavPort}/$ShareName
"@
    )
}

function Open-NasExplorerPath {
    param([string]$Letter, [string]$Username)
    $openPath = "${Letter}:\"
    if ($DeptFolderCode -and $Username) {
        $personal = Join-Path $openPath "$DeptFolderCode\$Username"
        if (Test-Path $personal) {
            $openPath = $personal
        } elseif (Test-Path (Join-Path $openPath $DeptFolderCode)) {
            $openPath = Join-Path $openPath $DeptFolderCode
        }
    }
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
    $shareLabel = if ($primaryShare) { $primaryShare } else { 'NAS' }
    $driveHint = "${DriveLetter}:"

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
    $lblSub.Text = if ($primaryShare) {
        "Tu dong gan o $driveHint ($shareLabel) - script $NasScriptVersion"
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
    $lblHint.Text = "WebDAV cong $WebDavPort - gan o $driveHint, mo Explorer sau khi dang nhap."
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
    $btnConnect.Text = "Ket noi NAS ($driveHint)"
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

        $shareName = Get-PrimaryNasShareName
        if (-not $shareName) {
            Set-Status 'Chua co share trong ZIP. Tai lai tu Portal (Thu vien -> Tai NAS).'
            return
        }

        $btnConnect.Enabled = $false
        $script:connectUser = $user
        $script:connectShare = $shareName
        Set-LogText -Text 'Dang ket noi NAS (toi da ~60s)...' -Level info
        [System.Windows.Forms.Application]::DoEvents()

        try {
            $result = Connect-JustPlayNasShare -Username $user -Password $tbPass.Text `
                -ShareName $shareName -Letter $DriveLetter
            $opened = Open-NasExplorerPath -Letter $DriveLetter -Username $user
            Write-Log "OK: $($result.Letter): -> $($result.RemotePath) ($($result.Method))"
            [System.Windows.Forms.MessageBox]::Show(
                "Da ket noi NAS thanh cong.`n`nO dia: $($result.Letter):`nShare: $shareName`nDa mo: $opened",
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
