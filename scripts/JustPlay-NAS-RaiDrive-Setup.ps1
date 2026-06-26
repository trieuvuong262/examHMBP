# JustPlay - tu dong gan o NAS qua SMB (cong 445). Cong 5678 tren Synology la WebDAV, khong phai SMB.
# User/pass = tai khoan Portal (LDAP). Khong can cau hinh RaiDrive thu cong.
#
# Chay: double-click JustPlay-NAS-RaiDrive-Setup.bat

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:Ps1Path = $MyInvocation.MyCommand.Path

$Server = '__NAS_SERVER__'
$PortRaw = '__NAS_PORT__'
$NasFallbackServer = '__NAS_FALLBACK_SERVER__'
$LdapDomain = '__NAS_LDAP_DOMAIN__'
$PortalPasswordUrl = '__PORTAL_PASSWORD_URL__'
$PortalUsernameHint = '__PORTAL_USERNAME__'
$NasSharesCsv = '__NAS_SHARES__'
$DeptFolderCode = '__NAS_DEPT_CODE__'
$DriveLetterRaw = '__NAS_DRIVE_LETTER__'
$BlockedDefaultPassword = 'justplay@123'

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
    return @($merged.ToArray())
}

$inlineShares = Read-InlineNasShares
$jsonConfig = Import-JustPlayNasConfig
if ($jsonConfig) {
    if ($jsonConfig.server) { $Server = [string]$jsonConfig.server }
    if ($null -ne $jsonConfig.port) { $PortRaw = [string]$jsonConfig.port }
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

$NasShareNames = Merge-ShareNameLists @($jsonShares, $inlineShares)
if ($NasShareNames.Count -gt 0) {
    $NasSharesCsv = ($NasShareNames -join ',')
}

if ($Server -eq '__NAS_SERVER__') { $Server = 'justplay.synology.me' }
if ($NasFallbackServer -eq '__NAS_FALLBACK_SERVER__' -or -not $NasFallbackServer) {
    $NasFallbackServer = '100.93.5.42'
}
if ($PortRaw -eq '__NAS_PORT__') { $Port = 445 } else { $Port = [int]$PortRaw }
# 5678 = WebDAV (Synology) — bo qua neu ZIP cu con ghi nham
if ($Port -eq 5678) { $Port = 445 }
if ($LdapDomain -eq '__NAS_LDAP_DOMAIN__') { $LdapDomain = 'ldap.justplay.local' }
if ($PortalPasswordUrl -eq '__PORTAL_PASSWORD_URL__') {
    $PortalPasswordUrl = 'https://portal.justplay.vn/accounts/password/change/'
}
if ($PortalUsernameHint -eq '__PORTAL_USERNAME__') { $PortalUsernameHint = '' }
if ($DeptFolderCode -eq '__NAS_DEPT_CODE__') { $DeptFolderCode = '' }
if ($DriveLetterRaw -eq '__NAS_DRIVE_LETTER__') { $DriveLetter = 'Z' } else { $DriveLetter = $DriveLetterRaw.Trim().ToUpperInvariant() }

function Test-JustPlayNasBundleReady {
    if ($NasShareNames.Count -ge 1) { return $true }
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
            if ($target -ne $HostName) {
                return $target
            }
            return $HostName
        } catch {
            continue
        } finally {
            $client.Close()
        }
    }
    throw "Khong mo duoc cong $NasPort toi $HostName (timeout ${TimeoutMs}ms)."
}

function Get-NasPortCandidates {
    # SMB chuan: 445. Khong thu 5678 (WebDAV).
    $ports = New-Object System.Collections.Generic.List[int]
    [void]$ports.Add(445)
    if ($Port -ne 445) {
        [void]$ports.Add($Port)
    }
    return @($ports.ToArray())
}

function Resolve-NasConnectPlans {
    $plans = New-Object System.Collections.Generic.List[object]
    $failures = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in (Get-NasServerCandidates)) {
        foreach ($nasPort in (Get-NasPortCandidates)) {
            try {
                $hostReach = Test-NasServerPort -HostName $candidate -NasPort $nasPort
                [void]$plans.Add([pscustomobject]@{ Host = [string]$hostReach; Port = [int]$nasPort })
            } catch {
                [void]$failures.Add("${candidate}:${nasPort} - $($_.Exception.Message)")
            }
        }
    }
    if ($plans.Count -lt 1) {
        $shareHint = if ($NasShareNames.Count -gt 0) { $NasShareNames[0] } else { 'TEN_SHARE' }
        throw @"
Khong ket noi duoc SMB toi NAS.
$($failures -join "`n")

Thu map thu cong trong Explorer: \\$Server\$shareHint (cua SMB 445).
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

function Format-NetArguments {
    param([string[]]$Args)
    ($Args | ForEach-Object {
        if ($_ -match '\s') { "`"$_`"" } else { $_ }
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
    $netArgs = @('use', $localPath, $RemotePath, "/user:$WinUser", $PlainPassword, '/persistent:yes')
    if ($UseTcpPort) { $netArgs += "/TCPPORT:$NasPort" }
    $null = Invoke-ProcessWithTimeout -FilePath 'net.exe' `
        -ArgumentList (Format-NetArguments $netArgs) `
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
        -PlainPassword $PlainPassword -UseTcpPort:$UseTcpPort -NasPort $Port
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
        -PlainPassword $plain -NasPort $Port
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
        "$LdapDomain\$Username",
        "$Username@$LdapDomain"
    )
    Remove-NasDriveMap -Letter $Letter
    $errors = New-Object System.Collections.Generic.List[string]

    foreach ($plan in $plans) {
        $resolvedServer = $plan.Host
        $connectPort = $plan.Port
        $remotePath = "\\$resolvedServer\$ShareName"
        $useTcpPort = ($connectPort -ne 445)

        foreach ($winUser in $winUsers) {
            Save-NasCredential -Target $resolvedServer -WinUser $winUser -PlainPassword $Password
            try {
                Invoke-NasSmbMappingTimed -Letter $Letter -RemotePath $remotePath -WinUser $winUser `
                    -PlainPassword $Password -NasPort $connectPort
                return @{
                    Letter = $Letter
                    RemotePath = $remotePath
                    WinUser = $winUser
                    Method = if ($connectPort -eq 445) { 'New-SmbMapping (445)' } else { "New-SmbMapping ($connectPort)" }
                }
            } catch {
                $errors.Add("New-SmbMapping ${resolvedServer}:${connectPort} ($winUser): $($_.Exception.Message)")
            }
            try {
                Invoke-NasNetUseTimed -Letter $Letter -RemotePath $remotePath -WinUser $winUser `
                    -PlainPassword $Password -UseTcpPort:$useTcpPort -NasPort $connectPort
                return @{
                    Letter = $Letter
                    RemotePath = $remotePath
                    WinUser = $winUser
                    Method = if ($useTcpPort) { "net use /TCPPORT:$connectPort" } else { 'net use (445)' }
                }
            } catch {
                $label = if ($useTcpPort) { "net use /TCPPORT:$connectPort" } else { 'net use (445)' }
                $errors.Add("${label} ${resolvedServer} ($winUser): $($_.Exception.Message)")
            }
        }
    }

    throw (@"
Khong ket noi duoc NAS.
Share: $ShareName
User: $Username
$($errors -join "`n")

Goi y: kiem tra mat khau Portal; thu map thu cong \server\share trong Explorer.
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

    $shareLabel = if ($NasShareNames.Count -gt 0) { $NasShareNames[0] } else { 'NAS' }
    $driveHint = "${DriveLetter}:"

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'JustPlay NAS'
    $form.Font = $fontUi
    $form.ClientSize = New-Object System.Drawing.Size(420, 430)
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
    $lblSub.Text = if ($NasShareNames.Count -gt 0) {
        "Tu dong gan o $driveHint ($shareLabel)"
    } else {
        'Chua co share trong ZIP - tai lai tu Portal (Thu vien -> Tai NAS)'
    }
    $lblSub.Font = $fontSub
    $lblSub.ForeColor = [System.Drawing.Color]::FromArgb(254, 226, 226)
    $lblSub.AutoSize = $true
    $lblSub.Location = New-Object System.Drawing.Point(30, 56)
    $header.Controls.Add($lblSub)

    $card = New-Object System.Windows.Forms.Panel
    $card.Location = New-Object System.Drawing.Point(24, 112)
    $card.Size = New-Object System.Drawing.Size(372, 228)
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
    $tbPass.Size = New-Object System.Drawing.Size(332, 28)
    $tbPass.UseSystemPasswordChar = $true
    $tbPass.BorderStyle = 'FixedSingle'
    $card.Controls.Add($tbPass)

    $lblHint = New-Object System.Windows.Forms.Label
    $lblHint.Text = 'He thong tu ket noi SMB va mo File Explorer sau khi dang nhap.'
    $lblHint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
    $lblHint.ForeColor = $jpMuted
    $lblHint.AutoSize = $false
    $lblHint.Size = New-Object System.Drawing.Size(332, 36)
    $lblHint.Location = New-Object System.Drawing.Point(20, 150)
    $card.Controls.Add($lblHint)

    $lblStatus = New-Object System.Windows.Forms.Label
    $lblStatus.Text = ''
    $lblStatus.Font = New-Object System.Drawing.Font('Segoe UI', 8.75)
    $lblStatus.ForeColor = $jpRed
    $lblStatus.AutoSize = $false
    $lblStatus.Size = New-Object System.Drawing.Size(332, 48)
    $lblStatus.Location = New-Object System.Drawing.Point(20, 186)
    $card.Controls.Add($lblStatus)

    $btnConnect = New-Object System.Windows.Forms.Button
    $btnConnect.Text = "Ket noi NAS ($driveHint)"
    $btnConnect.Font = New-Object System.Drawing.Font('Segoe UI', 10.5, [System.Drawing.FontStyle]::Bold)
    $btnConnect.FlatStyle = 'Flat'
    $btnConnect.FlatAppearance.BorderSize = 0
    $btnConnect.BackColor = $jpRed
    $btnConnect.ForeColor = [System.Drawing.Color]::White
    $btnConnect.Size = New-Object System.Drawing.Size(372, 44)
    $btnConnect.Location = New-Object System.Drawing.Point(24, 352)
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
    $linkChange.Location = New-Object System.Drawing.Point(24, 404)
    $linkChange.Cursor = [System.Windows.Forms.Cursors]::Hand
    $linkChange.Add_LinkClicked({
        Start-Process $PortalPasswordUrl
    })
    $form.Controls.Add($linkChange)

    $script:connectUser = ''
    $script:connectShare = ''

    function Set-Status([string]$Text) {
        $lblStatus.Text = $Text
        [System.Windows.Forms.Application]::DoEvents()
    }

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
        Set-Status ''
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

        $shareName = if ($NasShareNames.Count -gt 0) { $NasShareNames[0] } else { '' }
        if (-not $shareName) {
            Set-Status 'Chua co share trong ZIP. Tai lai tu Portal (Thu vien -> Tai NAS).'
            return
        }

        $btnConnect.Enabled = $false
        $script:connectUser = $user
        $script:connectShare = $shareName
        Set-Status 'Dang ket noi NAS (toi da ~60s)...'
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
