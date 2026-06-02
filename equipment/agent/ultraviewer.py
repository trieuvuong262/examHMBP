"""Đọc UltraViewer ID (PreferID registry) và mật khẩu cố định (cửa sổ app khi đang chạy)."""

from __future__ import annotations

import json
import platform
import re

from equipment.agent.core import run_powershell

_COLLECT_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @{ id = ''; password = '' }

function Is-Printable([string]$s) {
    if (-not $s) { return $false }
    foreach ($ch in $s.ToCharArray()) {
        $code = [int][char]$ch
        if ($code -lt 32 -or $code -gt 126) { return $false }
    }
    return $true
}

# --- ID: HKLM PreferID (Reg.ini thường rỗng trên bản 6.6.x) ---
foreach ($regPath in @(
    'HKLM:\SOFTWARE\WOW6432Node\UltraViewer',
    'HKLM:\Software\UltraViewer'
)) {
    if (-not (Test-Path $regPath)) { continue }
    try {
        $props = Get-ItemProperty $regPath -ErrorAction Stop
        if ($props.PreferID) {
            $uvId = ([string]$props.PreferID).Trim() -replace '\D', ''
            if ($uvId.Length -ge 6 -and $uvId.Length -le 12) {
                $out.id = $uvId
                break
            }
        }
    } catch {}
}

# --- Mật khẩu cố định: chỉ đọc từ cửa sổ UltraViewer (không lưu plaintext trong Reg.ini) ---
function Read-PasswordFromWindow {
    $names = @('UltraViewer_Desktop', 'UltraViewer')
    $proc = Get-Process -Name $names -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $proc) { return }

    try {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
    } catch { return }

    $ae = [System.Windows.Automation.AutomationElement]
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ProcessIdProperty, $proc.Id)
    $win = $ae::RootElement.FindFirst(
        [System.Windows.Automation.TreeScope]::Children, $cond)
    if (-not $win) { return }

    $editType = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
    $edits = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editType)

    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($el in $edits) {
        $val = ''
        try {
            $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            if ($vp) { $val = [string]$vp.Current.Value }
        } catch {}
        if (-not $val) { continue }
        if (-not (Is-Printable $val)) { continue }
        if ($val -eq $out.id) { continue }
        if ($val -match '^\d{1,5}$') { continue }
        if ($val.Length -ge 4 -and $val.Length -le 64) {
            [void]$candidates.Add($val)
        }
    }

    if ($candidates.Count -gt 0) {
        $best = $candidates | Sort-Object Length -Descending | Select-Object -First 1
        $out.password = $best
    }
}

$uvExe = @(
    "${env:ProgramFiles(x86)}\UltraViewer\UltraViewer_Desktop.exe",
    "$env:ProgramFiles\UltraViewer\UltraViewer_Desktop.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($uvExe -and -not (Get-Process -Name 'UltraViewer_Desktop','UltraViewer' -EA 0)) {
    Start-Process $uvExe -WindowStyle Normal
    Start-Sleep -Seconds 5
}

Read-PasswordFromWindow

$out | ConvertTo-Json -Compress
"""


def collect_ultraviewer() -> dict:
    if platform.system() != 'Windows':
        return {}
    raw = run_powershell(_COLLECT_PS, timeout=90)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    result = {}
    uv_id = re.sub(r'\D', '', (data.get('id') or '').strip())
    if uv_id and 6 <= len(uv_id) <= 12:
        result['ultraviewer_id'] = uv_id[:32]
    uv_pass = (data.get('password') or '').strip()
    if uv_pass and all(32 <= ord(c) <= 126 for c in uv_pass) and 4 <= len(uv_pass) <= 64:
        result['ultraviewer_password'] = uv_pass[:128]
    return result
