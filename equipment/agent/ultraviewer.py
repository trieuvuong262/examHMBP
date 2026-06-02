"""Đọc ID / mật khẩu UltraViewer trên Windows (registry, file, UI nếu đang chạy)."""

from __future__ import annotations

import json
import platform
import re

from equipment.agent.core import run_powershell

_COLLECT_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @{ id = ''; password = ''; source = '' }

function Set-Field([string]$key, [string]$val, [string]$src) {
    if (-not $val) { return }
    $val = $val.Trim()
    if (-not $val) { return }
    if (-not $out[$key]) {
        $out[$key] = $val
        if ($src -and -not $out.source) { $out.source = $src }
    }
}

function Test-Id([string]$s) {
    if (-not $s) { return $false }
    $d = ($s -replace '\D', '')
    return ($d.Length -ge 6 -and $d.Length -le 12)
}

function Normalize-Id([string]$s) {
    if (-not $s) { return '' }
    if ($s -match '^\d{6,12}$') { return $s }
    $d = ($s -replace '\D', '')
    if ($d.Length -ge 6 -and $d.Length -le 12) { return $d }
    return ''
}

function Scan-Text([string]$text, [string]$src) {
    if (-not $text) { return }
    foreach ($line in ($text -split "[\r\n]+")) {
        $line = $line.Trim()
        if (-not $line) { continue }
        if ($line -match '(?i)(?:id|clientid|yourid|partnerid|ultraviewerid|machineno|mayid)\s*[=:]\s*(\d{6,12})') {
            Set-Field 'id' $matches[1] $src
        }
        if ($line -match '(?i)(?:password|pass|matkhau|custompass|fixedpass|pwd)\s*[=:]\s*(.+)$') {
            Set-Field 'password' $matches[1].Trim() $src
        }
    }
    foreach ($m in [regex]::Matches($text, '\b\d{8,10}\b')) {
        if (-not $out.id) { Set-Field 'id' $m.Value $src }
    }
}

function Read-IniFile([string]$path) {
    if (-not (Test-Path $path)) { return }
    foreach ($enc in @('Unicode', 'UTF8', 'Default')) {
        try {
            $raw = [IO.File]::ReadAllText($path, [Text.Encoding]::$enc)
            Scan-Text $raw "ini:$([IO.Path]::GetFileName($path)):$enc"
        } catch {}
    }
    try {
        $bytes = [IO.File]::ReadAllBytes($path)
        $ascii = -join ($bytes | ForEach-Object { if ($_ -ge 32 -and $_ -le 126) { [char]$_ } else { ' ' } })
        Scan-Text $ascii "ini-bytes:$([IO.Path]::GetFileName($path))"
    } catch {}
}

$dirs = @(
    (Join-Path $env:APPDATA 'UltraViewer'),
    (Join-Path ${env:ProgramData} 'UltraViewer'),
    (Join-Path ${env:ProgramFiles(x86)} 'UltraViewer'),
    (Join-Path $env:ProgramFiles 'UltraViewer')
)
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem $dir -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Extension -match '\.(ini|txt|cfg|dat)$' -or $_.Name -match '^(?i)reg') {
            Read-IniFile $_.FullName
        }
    }
}

$regPaths = @(
    'HKCU:\Software\UltraViewer',
    'HKCU:\Software\VB and VBA Program Settings\UltraViewer_Desktop',
    'HKLM:\SOFTWARE\WOW6432Node\UltraViewer',
    'HKLM:\Software\UltraViewer'
)
foreach ($regPath in $regPaths) {
    try {
        $key = Get-Item $regPath -ErrorAction Stop
        foreach ($name in $key.Property) {
            $val = [string](Get-ItemProperty -Path $regPath -Name $name -ErrorAction SilentlyContinue).$name
            if (-not $val) { continue }
            if ($name -match '(?i)id|client') { Set-Field 'id' (Normalize-Id $val) "reg:$name" }
            if ($name -match '(?i)pass|pwd|matkhau') { Set-Field 'password' $val "reg:$name" }
        }
    } catch {}
}

function Read-UltraViewerWindow {
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
    $types = @(
        [System.Windows.Automation.ControlType]::Edit,
        [System.Windows.Automation.ControlType]::Text
    )
    foreach ($t in $types) {
        $tc = New-Object System.Windows.Automation.PropertyCondition(
            $ae::ControlTypeProperty, $t)
        $found = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tc)
        foreach ($el in $found) {
            $val = ''
            try {
                $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ($vp) { $val = $vp.Current.Value }
            } catch {}
            if (-not $val) {
                try { $val = $el.Current.Name } catch {}
            }
            if (-not $val) { continue }
            if (Test-Id $val) { Set-Field 'id' (Normalize-Id $val) 'ui' }
            elseif ($val.Length -ge 4 -and $val.Length -le 64 -and $val -notmatch '^\d+$') {
                Set-Field 'password' $val 'ui'
            }
        }
    }
}

$uvExe = @(
    (Join-Path ${env:ProgramFiles(x86)} 'UltraViewer\UltraViewer_Desktop.exe'),
    (Join-Path $env:ProgramFiles 'UltraViewer\UltraViewer_Desktop.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($uvExe -and -not (Get-Process -Name 'UltraViewer_Desktop','UltraViewer' -EA 0)) {
    Start-Process $uvExe -WindowStyle Minimized
    Start-Sleep -Seconds 4
}

Read-UltraViewerWindow

if ($out.id) { $out.id = Normalize-Id $out.id }

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
    uv_id = (data.get('id') or '').strip()
    uv_pass = (data.get('password') or '').strip()
    if uv_id and re.fullmatch(r'\d{6,12}', uv_id):
        result['ultraviewer_id'] = uv_id[:32]
    if uv_pass and len(uv_pass) >= 2:
        result['ultraviewer_password'] = uv_pass[:128]
    return result
