# Map Synology SMB từ Windows (tương đương RaiDrive: justplay.synology.me:5678).
# Tài khoản LDAP đồng bộ từ Portal — cùng username/mật khẩu đăng nhập Portal.
#
# Ví dụ (chạy PowerShell, không cần Admin trừ khi dùng portproxy):
#   .\JustPlay-NAS-Map-SMB.ps1 -Username vuonglnt -ShareName 07_SAN_XUAT -DriveLetter Z
#   .\JustPlay-NAS-Map-SMB.ps1 -Username vuonglnt -ShareName KD-MKT -DriveLetter Y -Persist
#
# Share theo phòng ban (tham khảo nas_storage/dept_nas_config.py):
#   TGD → 01_BAN_GIAM_DOC | HCNS → 02_HANH_CHINH_NHAN_SU | TCKT → 03_TAI_CHINH_KE_TOAN
#   MKT/KD-MKT → KD-MKT | RnD → 06_RnD_THIET_KE_SAN_PHAM | SX → 07_SAN_XUAT | IT → 10_HE_THONG_CNTT

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Username,

    [Parameter(Mandatory = $true)]
    [string]$ShareName,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Z]$')]
    [string]$DriveLetter,

    [string]$Server = 'justplay.synology.me',
    [int]$Port = 5678,
    [string]$Domain = 'ldap.justplay.local',

    [string]$Password,
    [switch]$Persist,
    [switch]$ReadOnly
)

$ErrorActionPreference = 'Stop'
$localPath = "${DriveLetter}:"
$remotePath = "\\$Server\$ShareName"
$winUser = "$Domain\$Username"
$ldapPrincipal = "$Username@$Domain"
$target = $Server

function Remove-ExistingMap {
    if (Test-Path $localPath) {
        & net use $localPath /delete /y 2>$null | Out-Null
    }
}

function Save-Credential {
    param([string]$PlainPassword)
    & cmdkey /delete:$target 2>$null | Out-Null
    $null = & cmdkey /add:$target /user:$winUser /pass:$PlainPassword
}

function Map-WithNetUse {
    param([string]$PlainPassword, [switch]$UseTcpPort)
    $args = @('use', $localPath, $remotePath, "/user:$winUser", $PlainPassword)
    if ($ReadOnly) { $args += '/readonly' }
    if ($Persist) { $args += '/persistent:yes' } else { $args += '/persistent:no' }
    if ($UseTcpPort) { $args += "/TCPPORT:$Port" }
    $output = & net @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "net use failed: $output"
    }
}

function Map-WithNewSmbMapping {
    param([securestring]$SecurePassword)
    $cred = New-Object System.Management.Automation.PSCredential($winUser, $SecurePassword)
    $params = @{
        LocalPath  = $localPath
        RemotePath = $remotePath
        TcpPort    = [uint16]$Port
        Credential = $cred
        Persistent = [bool]$Persist
    }
    if ($ReadOnly) {
        # New-SmbMapping không có readonly — dùng net use nếu cần readonly.
        throw 'ReadOnly: dùng net use'
    }
    New-SmbMapping @params | Out-Null
}

if (-not $Password) {
    $secure = Read-Host -AsSecureString "Mật khẩu Portal (LDAP) cho $ldapPrincipal"
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

Remove-ExistingMap
Save-Credential -PlainPassword $Password

$mapped = $false
$lastError = $null

# Windows 11 24H2+ / Server 2025: New-SmbMapping -TcpPort
try {
    $secure = ConvertTo-SecureString $Password -AsPlainText -Force
    Map-WithNewSmbMapping -SecurePassword $secure
    $mapped = $true
    $method = 'New-SmbMapping -TcpPort'
} catch {
    $lastError = $_.Exception.Message
}

if (-not $mapped) {
    try {
        Map-WithNetUse -PlainPassword $Password -UseTcpPort
        $mapped = $true
        $method = 'net use /TCPPORT'
    } catch {
        $lastError = "$lastError | $($_.Exception.Message)"
    }
}

if (-not $mapped) {
    try {
        # Một số bản Windows cũ: thử không chỉ định port (nếu NAS/QuickConnect redirect 445)
        Map-WithNetUse -PlainPassword $Password
        $mapped = $true
        $method = 'net use (port 445)'
    } catch {
        $lastError = "$lastError | $($_.Exception.Message)"
    }
}

if (-not $mapped) {
    throw @"
Không map được SMB.
Server: $Server port $Port
Share: $ShareName
User: $winUser (hoặc $ldapPrincipal)
Lỗi: $lastError

Gợi ý:
- Cập nhật Windows 11 24H2+ để dùng /TCPPORT hoặc New-SmbMapping -TcpPort
- Kiểm tra mật khẩu Portal (đồng bộ LDAP)
- Thử RaiDrive GUI: NAS → SMB, Address $Server, Port $Port, User $ldapPrincipal
"@
}

Write-Host "OK: $localPath -> $remotePath (port $Port, $method)"
Write-Host "User: $ldapPrincipal"
if ($Persist) {
    Write-Host "Đã lưu credential (cmdkey: $target) và map persistent."
}
