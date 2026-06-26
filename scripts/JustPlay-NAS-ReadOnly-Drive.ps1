# Map Synology share read-only on Windows — Explorer shows an error immediately
# instead of hanging when the user tries to create a folder.
#
# Usage (run as the logged-on user):
#   .\JustPlay-NAS-ReadOnly-Drive.ps1 -DriveLetter Z -UncPath "\\100.93.5.42\04_KINH_DOANH_CSKH"
#
# Optional: -Persist keeps the mapping after reboot (requires saved credentials).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Z]$')]
    [string]$DriveLetter,

    [Parameter(Mandatory = $true)]
    [string]$UncPath,

    [switch]$Persist
)

$ErrorActionPreference = 'Stop'
$target = "${DriveLetter}:"

function Show-JustPlayToast {
    param([string]$Title, [string]$Message)
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            $Message,
            $Title,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    } catch {
        Write-Host "$Title — $Message"
    }
}

if (Test-Path $target) {
    & net use $target /delete /y 2>$null | Out-Null
}

$args = @('use', $target, $UncPath, '/readonly')
if ($Persist) { $args += '/persistent:yes' }

$output = & net @args 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "net use failed: $output"
}

Show-JustPlayToast -Title 'JustPlay NAS — chỉ đọc' -Message @"
Đã map $target → $UncPath (chỉ đọc).

Nếu bạn tạo thư mục hoặc ghi file trong File Explorer, Windows sẽ báo lỗi ngay thay vì treo máy.

Chỉ dùng ổ này để xem/tải file. Muốn ghi file, liên hệ IT cấp quyền ghi trên Portal.
"@

Write-Host "OK: $target -> $UncPath (read-only)"
