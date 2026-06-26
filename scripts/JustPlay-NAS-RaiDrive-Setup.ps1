# JustPlay - tu dong gan o NAS qua SMB (justplay.synology.me:5678).
# User/pass = tai khoan Portal (LDAP). Khong can cau hinh RaiDrive thu cong.
#
# Chay: double-click JustPlay-NAS-RaiDrive-Setup.bat

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$Server = '__NAS_SERVER__'
$PortRaw = '__NAS_PORT__'
$LdapDomain = '__NAS_LDAP_DOMAIN__'
$PortalPasswordUrl = '__PORTAL_PASSWORD_URL__'
$PortalUsernameHint = '__PORTAL_USERNAME__'
$NasSharesCsv = '__NAS_SHARES__'
$DeptFolderCode = '__NAS_DEPT_CODE__'
$DriveLetterRaw = '__NAS_DRIVE_LETTER__'
$BlockedDefaultPassword = 'justplay@123'
$ConfigLoadedFromJson = $false

function Import-JustPlayNasConfig {
    $path = Join-Path $ScriptDir 'JustPlay-NAS-Config.json'
    if (-not (Test-Path $path)) { return $false }
    try {
        $cfg = Get-Content -Path $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $false
    }
    if ($cfg.server) { $script:Server = [string]$cfg.server }
    if ($null -ne $cfg.port) { $script:PortRaw = [string]$cfg.port }
    if ($cfg.ldap_domain) { $script:LdapDomain = [string]$cfg.ldap_domain }
    if ($cfg.portal_password_url) { $script:PortalPasswordUrl = [string]$cfg.portal_password_url }
    if ($cfg.portal_username) { $script:PortalUsernameHint = [string]$cfg.portal_username }
    if ($cfg.dept_folder_code) { $script:DeptFolderCode = [string]$cfg.dept_folder_code }
    if ($cfg.drive_letter) { $script:DriveLetterRaw = [string]$cfg.drive_letter }
    if ($cfg.shares) {
        $list = @($cfg.shares | ForEach-Object { [string]$_ } | Where-Object { $_.Trim() })
        $script:NasSharesCsv = ($list -join ',')
    }
    $script:ConfigLoadedFromJson = $true
    return $true
}

[void](Import-JustPlayNasConfig)

if ($Server -eq '__NAS_SERVER__') { $Server = 'justplay.synology.me' }
if ($PortRaw -eq '__NAS_PORT__') { $Port = 5678 } else { $Port = [int]$PortRaw }
if ($LdapDomain -eq '__NAS_LDAP_DOMAIN__') { $LdapDomain = 'ldap.justplay.local' }
if ($PortalPasswordUrl -eq '__PORTAL_PASSWORD_URL__') {
    $PortalPasswordUrl = 'https://portal.justplay.vn/accounts/password/change/'
}
if ($PortalUsernameHint -eq '__PORTAL_USERNAME__') { $PortalUsernameHint = '' }
if ($NasSharesCsv -eq '__NAS_SHARES__') { $NasSharesCsv = '' }
if ($DeptFolderCode -eq '__NAS_DEPT_CODE__') { $DeptFolderCode = '' }
if ($DriveLetterRaw -eq '__NAS_DRIVE_LETTER__') { $DriveLetter = 'Z' } else { $DriveLetter = $DriveLetterRaw.Trim().ToUpperInvariant() }

$NasShareNames = @(
    $NasSharesCsv -split ',' |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ }
)

function Test-JustPlayNasBundleReady {
    if (-not $ConfigLoadedFromJson) { return $false }
    if ($NasShareNames.Count -lt 1) { return $false }
    if ($Server -match '^__.+__$') { return $false }
    return $true
}

function Show-JustPlayNasBundleError {
    Add-Type -AssemblyName System.Windows.Forms
    $msg = @"
Bo cai chua duoc dong goi tu Portal (thieu JustPlay-NAS-Config.json hoac chua co share NAS).

Vui long:
1. Dang nhap Portal -> Thu vien -> Tai NAS
2. Tai file ZIP moi
3. Giai nen TOAN BO (khong chi copy file .ps1)
4. Chay JustPlay-NAS-RaiDrive-Setup.bat trong thu muc vua giai nen

Neu da lam dung ma van loi, lien he IT de gan phong ban / thu muc NAS.
"@
    [System.Windows.Forms.MessageBox]::Show($msg, 'JustPlay NAS', 'OK', 'Error') | Out-Null
}

function Write-Log([string]$Message) {
    Write-Host "[JustPlay] $Message"
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

function Invoke-NasNetUse {
    param(
        [string]$Letter,
        [string]$RemotePath,
        [string]$WinUser,
        [string]$PlainPassword,
        [switch]$UseTcpPort
    )
    $localPath = "${Letter}:"
    $args = @('use', $localPath, $RemotePath, "/user:$WinUser", $PlainPassword, '/persistent:yes')
    if ($UseTcpPort) { $args += "/TCPPORT:$Port" }
    $output = & net @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "net use: $output"
    }
}

function Invoke-NasSmbMapping {
    param(
        [string]$Letter,
        [string]$RemotePath,
        [string]$WinUser,
        [securestring]$SecurePassword
    )
    $cred = New-Object System.Management.Automation.PSCredential($WinUser, $SecurePassword)
    New-SmbMapping -LocalPath "${Letter}:" -RemotePath $RemotePath -TcpPort ([uint16]$Port) `
        -Credential $cred -Persistent $true -ErrorAction Stop | Out-Null
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
    $remotePath = "\\$Server\$ShareName"
    $winUsers = @(
        "$LdapDomain\$Username",
        "$Username@$LdapDomain"
    )
    Remove-NasDriveMap -Letter $Letter
    $secure = ConvertTo-SecureString $Password -AsPlainText -Force
    $errors = New-Object System.Collections.Generic.List[string]

    foreach ($winUser in $winUsers) {
        Save-NasCredential -Target $Server -WinUser $winUser -PlainPassword $Password
        try {
            Invoke-NasSmbMapping -Letter $Letter -RemotePath $remotePath -WinUser $winUser -SecurePassword $secure
            return @{
                Letter = $Letter
                RemotePath = $remotePath
                WinUser = $winUser
                Method = 'New-SmbMapping'
            }
        } catch {
            $errors.Add("New-SmbMapping ($winUser): $($_.Exception.Message)")
        }
        try {
            Invoke-NasNetUse -Letter $Letter -RemotePath $remotePath -WinUser $winUser `
                -PlainPassword $Password -UseTcpPort
            return @{
                Letter = $Letter
                RemotePath = $remotePath
                WinUser = $winUser
                Method = 'net use /TCPPORT'
            }
        } catch {
            $errors.Add("net use /TCPPORT ($winUser): $($_.Exception.Message)")
        }
        try {
            Invoke-NasNetUse -Letter $Letter -RemotePath $remotePath -WinUser $winUser `
                -PlainPassword $Password
            return @{
                Letter = $Letter
                RemotePath = $remotePath
                WinUser = $winUser
                Method = 'net use'
            }
        } catch {
            $errors.Add("net use ($winUser): $($_.Exception.Message)")
        }
    }

    throw (@"
Khong ket noi duoc NAS.
Share: $ShareName
Server: $Server port $Port
User: $Username
$($errors -join "`n")

Goi y: cap nhat Windows 11 24H2+ hoac kiem tra mat khau Portal.
"@)
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

    function Set-Status([string]$Text) {
        $lblStatus.Text = $Text
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
        $btnConnect.Enabled = $false
        Set-Status 'Dang ket noi NAS...'
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
            Set-Status $_.Exception.Message
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
