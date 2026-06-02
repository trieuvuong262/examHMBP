"""Đọc ID / mật khẩu UltraViewer trên Windows (nếu đã cài)."""

from __future__ import annotations

import json
import platform

from equipment.agent.core import run_powershell

_COLLECT_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @{ id = ''; password = '' }

function Set-IfEmpty([string]$key, [string]$val) {
    if (-not $val) { return }
    if (-not $out[$key]) { $out[$key] = $val.Trim() }
}

$iniPaths = @(
    (Join-Path $env:APPDATA 'UltraViewer\Reg.ini'),
    (Join-Path $env:APPDATA 'UltraViewer\Reg2.ini'),
    (Join-Path $env:APPDATA 'UltraViewer\Reg3.ini'),
    (Join-Path $env:APPDATA 'UltraViewer\TempPass.ini')
)
foreach ($path in $iniPaths) {
    if (-not (Test-Path $path)) { continue }
    Get-Content $path | ForEach-Object {
        $line = $_.Trim()
        if ($line -match '^(?i)(id|clientid|yourid|ultraviewerid)\s*=\s*(.+)$') {
            Set-IfEmpty 'id' $matches[2]
        }
        if ($line -match '^(?i)(password|pass|matkhau|custompass|fixedpass)\s*=\s*(.+)$') {
            Set-IfEmpty 'password' $matches[2]
        }
    }
}

$regPaths = @(
    'HKCU:\Software\UltraViewer',
    'HKLM:\SOFTWARE\WOW6432Node\UltraViewer',
    'HKLM:\Software\UltraViewer'
)
foreach ($regPath in $regPaths) {
    $props = Get-ItemProperty $regPath -ErrorAction SilentlyContinue
    if (-not $props) { continue }
    foreach ($name in $props.PSObject.Properties.Name) {
        if ($name -match '^(?i)(id|clientid|yourid)$') {
            Set-IfEmpty 'id' ([string]$props.$name)
        }
        if ($name -match '^(?i)(password|pass|custompassword|fixedpassword)$') {
            Set-IfEmpty 'password' ([string]$props.$name)
        }
    }
}

if ($out.id -match '^\d+$' -and $out.id.Length -ge 6) {
    # giữ
} elseif ($out.id) {
    $digits = ($out.id -replace '\D', '')
    if ($digits.Length -ge 6) { $out.id = $digits }
}

$out | ConvertTo-Json -Compress
"""


def collect_ultraviewer() -> dict:
    if platform.system() != 'Windows':
        return {}
    raw = run_powershell(_COLLECT_PS)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    result = {}
    uv_id = (data.get('id') or '').strip()
    uv_pass = (data.get('password') or '').strip()
    if uv_id:
        result['ultraviewer_id'] = uv_id[:32]
    if uv_pass:
        result['ultraviewer_password'] = uv_pass[:128]
    return result
