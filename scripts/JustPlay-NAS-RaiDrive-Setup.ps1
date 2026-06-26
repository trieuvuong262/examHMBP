# JustPlay — tai RaiDrive, cai dat, huong dan ket noi Synology SMB (justplay.synology.me:5678).
# User/pass = tai khoan Portal (LDAP: username@ldap.justplay.local).
#
# Chay: double-click JustPlay-NAS-RaiDrive-Setup.bat

$ErrorActionPreference = 'Stop'

$Server = 'justplay.synology.me'
$Port = 5678
$LdapDomain = 'ldap.justplay.local'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TempDir = Join-Path $env:TEMP 'JustPlay-RaiDrive'
$InstallerName = 'RaiDrive_x64.exe'
$LocalInstaller = Join-Path $ScriptDir $InstallerName
$DownloadedInstaller = Join-Path $TempDir $InstallerName

$DownloadUrls = @(
    (Join-Path $ScriptDir $InstallerName),
    'https://www.raidrive.com/static/installer/RaiDrive_x64.exe'
)

function Write-Log([string]$Message) {
    Write-Host "[JustPlay] $Message"
}

function Test-RaiDriveInstalled {
    $candidates = @(
        "${env:ProgramFiles}\OpenBoxLab\RaiDrive\RaiDrive.exe",
        "${env:ProgramFiles(x86)}\OpenBoxLab\RaiDrive\RaiDrive.exe",
        "${env:LocalAppData}\Programs\OpenBoxLab\RaiDrive\RaiDrive.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    $uninstall = Get-ChildItem 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
        Where-Object { $_.GetValue('DisplayName') -like 'RaiDrive*' } |
        Select-Object -First 1
    if ($uninstall) {
        $icon = $uninstall.GetValue('DisplayIcon')
        if ($icon -and (Test-Path ($icon -replace ',.*$',''))) {
            return ($icon -replace ',.*$','')
        }
    }
    return $null
}

function Get-InstallerPath {
    foreach ($url in $DownloadUrls) {
        if ($url -and (Test-Path $url)) {
            Write-Log "Dung file cai dat co san: $url"
            return $url
        }
    }
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
    Write-Log "Dang tai RaiDrive tu raidrive.com ..."
    try {
        Invoke-WebRequest -Uri 'https://www.raidrive.com/download' -OutFile $DownloadedInstaller -UseBasicParsing
        if ((Get-Item $DownloadedInstaller).Length -gt 1MB) {
            return $DownloadedInstaller
        }
    } catch {
        Write-Log "Tai qua trang download that bai: $($_.Exception.Message)"
    }
    throw @"
Không tải được RaiDrive.
IT có thể đặt file $InstallerName cùng thư mục với file .bat
hoặc tải thủ công: https://www.raidrive.com/download
"@
}

function Install-RaiDrive([string]$InstallerPath) {
    if (Test-RaiDriveInstalled) {
        Write-Log 'RaiDrive da duoc cai dat.'
        return
    }
    Write-Log "Cai dat silent: $InstallerPath"
    $proc = Start-Process -FilePath $InstallerPath -ArgumentList '/qn', '/norestart' -Wait -PassThru
    if ($proc.ExitCode -notin 0, 3010, 1641) {
        Write-Log "Silent /qn ma $($proc.ExitCode) — thu cai dat GUI ..."
        Start-Process -FilePath $InstallerPath -Wait
    }
    if (-not (Test-RaiDriveInstalled)) {
        throw 'Cài đặt RaiDrive chưa xong. Hoàn tất wizard cài đặt rồi chạy lại script.'
    }
}

function Show-JustPlayRaiDriveDialog {
    param([string]$RaiDriveExe)

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'JustPlay NAS — RaiDrive'
    $form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $form.Size = New-Object System.Drawing.Size(580, 540)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $y = 12

    $lblIntro = New-Object System.Windows.Forms.Label
    $lblIntro.Size = New-Object System.Drawing.Size(540, 50)
    $lblIntro.Location = New-Object System.Drawing.Point(12, $y)
    $lblIntro.Text = 'RaiDrive đã sẵn sàng. Nhập tài khoản Portal (đồng bộ LDAP), sau đó bấm Mở RaiDrive để thêm ổ NAS.'
    $form.Controls.Add($lblIntro)
    $y += 58

    function Add-ReadOnlyField {
        param([string]$Label, [string]$Value)
        $l = New-Object System.Windows.Forms.Label
        $l.Text = $Label
        $l.AutoSize = $true
        $l.Location = New-Object System.Drawing.Point(12, $script:fieldY)
        $form.Controls.Add($l)
        $script:fieldY += 22
        $t = New-Object System.Windows.Forms.TextBox
        $t.Text = $Value
        $t.ReadOnly = $true
        $t.Width = 520
        $t.BackColor = [System.Drawing.Color]::FromArgb(245, 245, 245)
        $t.Location = New-Object System.Drawing.Point(12, $script:fieldY)
        $form.Controls.Add($t)
        $script:fieldY += 34
    }

    $script:fieldY = $y
    Add-ReadOnlyField 'Máy chủ (Server)' $Server
    Add-ReadOnlyField 'Cổng (Port)' "$Port"
    Add-ReadOnlyField 'Domain LDAP' $LdapDomain

    $lUser = New-Object System.Windows.Forms.Label
    $lUser.Text = 'Tên đăng nhập Portal'
    $lUser.AutoSize = $true
    $lUser.Location = New-Object System.Drawing.Point(12, $script:fieldY)
    $form.Controls.Add($lUser)
    $script:fieldY += 22
    $tbUser = New-Object System.Windows.Forms.TextBox
    $tbUser.Width = 520
    $tbUser.Location = New-Object System.Drawing.Point(12, $script:fieldY)
    $form.Controls.Add($tbUser)
    $script:fieldY += 34

    $lPass = New-Object System.Windows.Forms.Label
    $lPass.Text = 'Mật khẩu Portal'
    $lPass.AutoSize = $true
    $lPass.Location = New-Object System.Drawing.Point(12, $script:fieldY)
    $form.Controls.Add($lPass)
    $script:fieldY += 22
    $tbPass = New-Object System.Windows.Forms.TextBox
    $tbPass.Width = 520
    $tbPass.UseSystemPasswordChar = $true
    $tbPass.Location = New-Object System.Drawing.Point(12, $script:fieldY)
    $form.Controls.Add($tbPass)
    $script:fieldY += 40

    $lblSteps = New-Object System.Windows.Forms.Label
    $lblSteps.Size = New-Object System.Drawing.Size(540, 120)
    $lblSteps.Location = New-Object System.Drawing.Point(12, $script:fieldY)
    $lblSteps.Text = @"
Trong RaiDrive:
1. Bấm Add (+) → Storage → NAS → Synology (hoặc SMB)
2. Address: $Server    Port: $Port
3. Account: [username]@$LdapDomain
4. Password: mật khẩu Portal
5. Chọn share phòng ban → OK → Connect
"@
    $form.Controls.Add($lblSteps)
    $script:fieldY += 128

    $btnCopy = New-Object System.Windows.Forms.Button
    $btnCopy.Text = 'Sao chép hướng dẫn'
    $btnCopy.Size = New-Object System.Drawing.Size(150, 34)
    $btnCopy.Location = New-Object System.Drawing.Point(12, $script:fieldY)
    $btnCopy.Add_Click({
        $u = $tbUser.Text.Trim()
        $principal = if ($u) { "$u@$LdapDomain" } else { "[username]@$LdapDomain" }
        $clip = @"
JustPlay NAS (RaiDrive)
Server: $Server
Port: $Port
Account: $principal
Password: (mật khẩu Portal)

Bước: Add → NAS → Synology/SMB → điền thông tin → Connect
"@
        [System.Windows.Forms.Clipboard]::SetText($clip)
        [System.Windows.Forms.MessageBox]::Show('Đã sao chép vào clipboard.', 'JustPlay NAS', 'OK', 'Information') | Out-Null
    })
    $form.Controls.Add($btnCopy)

    $btnOpen = New-Object System.Windows.Forms.Button
    $btnOpen.Text = 'Mở RaiDrive'
    $btnOpen.Size = New-Object System.Drawing.Size(130, 34)
    $btnOpen.Location = New-Object System.Drawing.Point(175, $script:fieldY)
    $btnOpen.Add_Click({
        if (-not $tbUser.Text.Trim()) {
            [System.Windows.Forms.MessageBox]::Show('Vui lòng nhập tên đăng nhập Portal.', 'JustPlay NAS', 'OK', 'Warning') | Out-Null
            $tbUser.Focus() | Out-Null
            return
        }
        if (-not $tbPass.Text) {
            $ans = [System.Windows.Forms.MessageBox]::Show(
                'Chưa nhập mật khẩu. Bạn sẽ nhập trực tiếp trong RaiDrive?',
                'JustPlay NAS', 'YesNo', 'Question'
            )
            if ($ans -ne 'Yes') { return }
        }
        $principal = "$($tbUser.Text.Trim())@$LdapDomain"
        [System.Windows.Forms.MessageBox]::Show(
            "Trong RaiDrive, dùng:`n`nServer: $Server`nPort: $Port`nAccount: $principal`nPassword: mật khẩu Portal",
            'JustPlay NAS — thông tin đăng nhập',
            'OK',
            'Information'
        ) | Out-Null
        Start-Process $RaiDriveExe
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    })
    $form.Controls.Add($btnOpen)

    $btnClose = New-Object System.Windows.Forms.Button
    $btnClose.Text = 'Đóng'
    $btnClose.Size = New-Object System.Drawing.Size(90, 34)
    $btnClose.Location = New-Object System.Drawing.Point(460, $script:fieldY)
    $btnClose.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($btnClose)

    $form.AcceptButton = $btnOpen
    $form.CancelButton = $btnClose
    [void]$form.ShowDialog()
}

try {
    $existing = Test-RaiDriveInstalled
    if (-not $existing) {
        $installer = Get-InstallerPath
        Install-RaiDrive -InstallerPath $installer
        $existing = Test-RaiDriveInstalled
    }
    if (-not $existing) {
        throw 'Không tìm thấy RaiDrive sau khi cài đặt.'
    }
    Write-Log "RaiDrive: $existing"
    Show-JustPlayRaiDriveDialog -RaiDriveExe $existing
    Write-Log 'Hoàn tất.'
    exit 0
} catch {
    [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
    [System.Windows.Forms.MessageBox]::Show(
        $_.Exception.Message,
        'JustPlay NAS — lỗi',
        'OK',
        'Error'
    ) | Out-Null
    Write-Error $_
    exit 1
}
