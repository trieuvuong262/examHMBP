"""Đọc UltraViewer ID (PreferID registry) và mật khẩu cố định (cửa sổ app khi đang chạy)."""

from __future__ import annotations

import base64
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

function Add-Candidate([System.Collections.Generic.List[string]]$list, [string]$val, [string]$skipId) {
    if (-not $val) { return }
    if (-not (Is-Printable $val)) { return }
    if ($val -eq $skipId) { return }
    if ($val -match '^\d{1,5}$') { return }
    if ($val.Length -ge 4 -and $val.Length -le 64) {
        if (-not $list.Contains($val)) { [void]$list.Add($val) }
    }
}

# --- ID: HKLM PreferID (Reg.ini thường rỗng trên bản 6.6.x) ---
foreach ($regPath in @(
    'HKLM:\SOFTWARE\WOW6432Node\UltraViewer',
    'HKLM:\Software\UltraViewer',
    'HKCU:\Software\UltraViewer'
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

# --- Mật khẩu cố định: UI Automation (Edit + Text trên cửa sổ UltraViewer) ---
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

    $candidates = New-Object System.Collections.Generic.List[string]
    $skipId = $out.id

    $editType = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
    $edits = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editType)
    foreach ($el in $edits) {
        $val = ''
        try {
            $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            if ($vp) { $val = [string]$vp.Current.Value }
        } catch {}
        Add-Candidate $candidates $val $skipId
    }

    $textType = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Text)
    $texts = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $textType)
    foreach ($el in $texts) {
        foreach ($propName in @('Name', 'HelpText')) {
            $val = [string]$el.Current.$propName
            Add-Candidate $candidates $val $skipId
        }
    }

    $trueCond = [System.Windows.Automation.Condition]::TrueCondition
    $all = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $trueCond)
    foreach ($el in $all) {
        $name = [string]$el.Current.Name
        if ($name -match '(?i)(pass|password|mật khẩu|mat khau)') {
            $sib = $el
            for ($i = 0; $i -lt 3; $i++) {
                try {
                    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
                    $sib = $walker.GetNextSibling($sib)
                    if ($sib) {
                        $n = [string]$sib.Current.Name
                        Add-Candidate $candidates $n $skipId
                    }
                } catch { break }
            }
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
    Start-Sleep -Seconds 8
}

Read-PasswordFromWindow

if ($env:JP_DIR -and ($out.id -or $out.password)) {
    $sidecar = @{
        ultraviewer_id = $out.id
        ultraviewer_password = $out.password
    }
    $sidecarPath = Join-Path $env:JP_DIR 'ultraviewer_sidecar.json'
    $sidecar | ConvertTo-Json -Compress | Set-Content -Path $sidecarPath -Encoding UTF8 -Force
}

$out | ConvertTo-Json -Compress
"""


def ultraviewer_collect_b64() -> str:
    """PowerShell -EncodedCommand cho file .cmd cài agent."""
    return base64.b64encode(_COLLECT_PS.encode('utf-16le')).decode('ascii')


def collect_ultraviewer() -> dict:
    if platform.system() != 'Windows':
        return {}
    import os

    from equipment.agent.core import exe_dir

    os.environ['JP_DIR'] = str(exe_dir())
    raw = run_powershell(_COLLECT_PS, timeout=120)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return _normalize_uv_payload(data)


def load_ultraviewer_sidecar(agent_dir=None) -> dict:
    """Đọc ultraviewer_sidecar.json (file .cmd ghi trước khi chạy exe)."""
    from equipment.agent.core import exe_dir

    base = agent_dir if agent_dir is not None else exe_dir()
    path = base / 'ultraviewer_sidecar.json'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (json.JSONDecodeError, OSError):
        return {}
    return _normalize_uv_payload(data)


def _normalize_uv_payload(data: dict) -> dict:
    result = {}
    uv_id = re.sub(
        r'\D',
        '',
        (data.get('ultraviewer_id') or data.get('id') or '').strip(),
    )
    if uv_id and 6 <= len(uv_id) <= 12:
        result['ultraviewer_id'] = uv_id[:32]
    uv_pass = (data.get('ultraviewer_password') or data.get('password') or '').strip()
    if uv_pass and all(32 <= ord(c) <= 126 for c in uv_pass) and 4 <= len(uv_pass) <= 64:
        result['ultraviewer_password'] = uv_pass[:128]
    return result
