"""UltraViewer: đặt mật khẩu cố định chuẩn IT + đọc PreferID + báo lên portal."""

from __future__ import annotations

import base64
import json
import os
import platform
import re

from equipment.agent.core import run_powershell

DEFAULT_ULTRAVIEWER_FIXED_PASSWORD = '123123sS'
DEFAULT_ULTRAVIEWER_SETUP_URL = (
    'https://www.ultraviewer.net/en/UltraViewer_setup_6.6_en.exe'
)

_COLLECT_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @{ id = ''; password = '' }

$targetPwd = $env:JP_UV_PASSWORD
if (-not $targetPwd) { $targetPwd = 'DEFAULT_PWD_PLACEHOLDER' }

function Get-UvDesktopExe {
    @(
        "${env:ProgramFiles(x86)}\UltraViewer\UltraViewer_Desktop.exe",
        "$env:ProgramFiles\UltraViewer\UltraViewer_Desktop.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Install-UltraViewerIfMissing {
    if (Get-UvDesktopExe) { return $true }
    $setupUrl = $env:JP_UV_SETUP_URL
    if (-not $setupUrl) { $setupUrl = 'DEFAULT_SETUP_URL_PLACEHOLDER' }
    $dir = $env:JP_DIR
    if (-not $dir) { $dir = $env:TEMP }
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $setup = Join-Path $dir 'UltraViewer_setup.exe'
    $ok = $false
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $setupUrl -OutFile $setup -UseBasicParsing
        $ok = Test-Path $setup
    } catch {}
    if (-not $ok) {
        $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
        if (Test-Path $curl) {
            & $curl -fsSL $setupUrl -o $setup 2>$null
            $ok = Test-Path $setup
        }
    }
    if (-not $ok) { return $false }
    $args = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    $proc = Start-Process -FilePath $setup -ArgumentList $args -Wait -PassThru -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    Remove-Item $setup -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 50; $i++) {
        if (Get-UvDesktopExe) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Read-PreferId {
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
                    return
                }
            }
        } catch {}
    }
}

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

[void](Install-UltraViewerIfMissing)
for ($r = 0; $r -lt 40; $r++) {
    Read-PreferId
    if ($out.id) { break }
    Start-Sleep -Seconds 3
}

function Set-UltraViewerFixedPassword([string]$pwd) {
    $names = @('UltraViewer_Desktop', 'UltraViewer')
    $proc = Get-Process -Name $names -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $proc) { return $false }

    try {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        Add-Type @'
using System;
using System.Runtime.InteropServices;
public class JpWin32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
'@
    } catch { return $false }

    $ae = [System.Windows.Automation.AutomationElement]
    $procCond = New-Object System.Windows.Automation.PropertyCondition($ae::ProcessIdProperty, $proc.Id)
    $win = $ae::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $procCond)
    if (-not $win) { return $false }

    $hwnd = [IntPtr]$win.Current.NativeWindowHandle
    if ($hwnd -ne [IntPtr]::Zero) {
        [void][JpWin32]::ShowWindow($hwnd, 9)
        [void][JpWin32]::SetForegroundWindow($hwnd)
        Start-Sleep -Milliseconds 600
    }

    $btnCond = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    $buttons = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)

    $clicked = $false
    foreach ($btn in $buttons) {
        $blob = ([string]$btn.Current.Name + ' ' + [string]$btn.Current.HelpText + ' ' + [string]$btn.Current.AutomationId)
        if ($blob -match '(?i)(custom|fixed|permanent|private|personal|rieng).*pass|pass.*(custom|fixed|permanent)|\bkey\b|chìa|chia khoa|mat khau|password') {
            try {
                $inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                if ($inv) { $inv.Invoke(); $clicked = $true; break }
            } catch {}
        }
    }
    if (-not $clicked) {
        foreach ($btn in $buttons) {
            $rect = $btn.Current.BoundingRectangle
            if ($rect.Width -gt 0 -and $rect.Width -le 48 -and $rect.Height -le 48) {
                try {
                    $inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                    if ($inv) { $inv.Invoke(); $clicked = $true; break }
                } catch {}
            }
        }
    }
    Start-Sleep -Seconds 2

    $editCond = New-Object System.Windows.Automation.PropertyCondition(
        $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
    $allEdits = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants, $editCond)
    $pwdEdits = @()
    foreach ($el in $allEdits) {
        if ($el.Current.ProcessId -eq $proc.Id) { $pwdEdits += $el }
    }

    $filled = 0
    foreach ($el in $pwdEdits) {
        try {
            $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            if ($vp) {
                $vp.SetValue($pwd)
                $filled++
            }
        } catch {}
        if ($filled -ge 2) { break }
    }
    if ($filled -lt 1) { return $false }

    Start-Sleep -Milliseconds 500
    $allBtns = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants, $btnCond)
    foreach ($btn in $allBtns) {
        if ($btn.Current.ProcessId -ne $proc.Id) { continue }
        $n = [string]$btn.Current.Name
        if ($n -match '^(OK|Ok|Yes|Save|Lưu|Luu|Đồng ý|Dong y)$') {
            try {
                $inv = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                if ($inv) { $inv.Invoke(); return $true }
            } catch {}
        }
    }
    return $true
}

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

    if ($candidates.Count -gt 0) {
        $best = $candidates | Sort-Object Length -Descending | Select-Object -First 1
        $out.password = $best
    }
}

$uvExe = Get-UvDesktopExe

if ($uvExe -and -not (Get-Process -Name 'UltraViewer_Desktop','UltraViewer' -EA 0)) {
    Start-Process $uvExe -WindowStyle Normal
    Start-Sleep -Seconds 8
}

if ($uvExe) {
    [void](Set-UltraViewerFixedPassword $targetPwd)
    Start-Sleep -Seconds 1
}

Read-PasswordFromWindow
$out.password = $targetPwd

if ($env:JP_DIR) {
    $sidecar = @{
        ultraviewer_id = $out.id
        ultraviewer_password = $out.password
    }
    $sidecarPath = Join-Path $env:JP_DIR 'ultraviewer_sidecar.json'
    $sidecar | ConvertTo-Json -Compress | Set-Content -Path $sidecarPath -Encoding UTF8 -Force
}

$out | ConvertTo-Json -Compress
"""


def resolve_ultraviewer_password() -> str:
    pwd = os.environ.get('JP_UV_PASSWORD', '').strip()
    if pwd:
        return pwd[:128]
    try:
        from django.conf import settings

        return (
            getattr(settings, 'EQUIPMENT_ULTRAVIEWER_FIXED_PASSWORD', None)
            or DEFAULT_ULTRAVIEWER_FIXED_PASSWORD
        )[:128]
    except Exception:
        return DEFAULT_ULTRAVIEWER_FIXED_PASSWORD


def resolve_ultraviewer_setup_url() -> str:
    url = os.environ.get('JP_UV_SETUP_URL', '').strip()
    if url:
        return url
    try:
        from django.conf import settings

        custom = getattr(settings, 'EQUIPMENT_ULTRAVIEWER_SETUP_URL', '').strip()
        if custom:
            return custom
        base = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/')
        if base:
            return f'{base}/static/equipment/UltraViewer_setup_en.exe'
    except Exception:
        pass
    return DEFAULT_ULTRAVIEWER_SETUP_URL


def build_collect_ps(
    fixed_password: str | None = None,
    setup_url: str | None = None,
) -> str:
    pwd = (fixed_password or resolve_ultraviewer_password()).replace("'", "''")
    setup = (setup_url or resolve_ultraviewer_setup_url()).replace("'", "''")
    return (
        _COLLECT_PS.replace('DEFAULT_PWD_PLACEHOLDER', pwd)
        .replace('DEFAULT_SETUP_URL_PLACEHOLDER', setup)
    )


def ultraviewer_collect_b64(
    fixed_password: str | None = None,
    setup_url: str | None = None,
) -> str:
    """PowerShell -EncodedCommand cho file .cmd cài agent."""
    script = build_collect_ps(fixed_password, setup_url)
    return base64.b64encode(script.encode('utf-16le')).decode('ascii')


def collect_ultraviewer() -> dict:
    if platform.system() != 'Windows':
        return {}
    from equipment.agent.core import exe_dir

    os.environ['JP_DIR'] = str(exe_dir())
    if not os.environ.get('JP_UV_PASSWORD'):
        os.environ['JP_UV_PASSWORD'] = resolve_ultraviewer_password()
    if not os.environ.get('JP_UV_SETUP_URL'):
        os.environ['JP_UV_SETUP_URL'] = resolve_ultraviewer_setup_url()
    raw = run_powershell(build_collect_ps(), timeout=300)
    if not raw:
        return _fallback_payload()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_payload()
    result = _normalize_uv_payload(data)
    if not result.get('ultraviewer_password'):
        result['ultraviewer_password'] = resolve_ultraviewer_password()
    return result


def _fallback_payload() -> dict:
    """Registry ID + mật khẩu chuẩn khi UI Automation thất bại."""
    from equipment.agent.core import run_powershell

    rid = ''
    raw = run_powershell(
        "(Get-ItemProperty 'HKLM:\\SOFTWARE\\WOW6432Node\\UltraViewer' -EA 0).PreferID",
        timeout=15,
    )
    if raw:
        uv_id = re.sub(r'\D', '', raw.strip())
        if uv_id and 6 <= len(uv_id) <= 12:
            rid = uv_id
    out = {'ultraviewer_password': resolve_ultraviewer_password()}
    if rid:
        out['ultraviewer_id'] = rid[:32]
    return out


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
    result = _normalize_uv_payload(data)
    if not result.get('ultraviewer_password'):
        result['ultraviewer_password'] = resolve_ultraviewer_password()
    return result


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
