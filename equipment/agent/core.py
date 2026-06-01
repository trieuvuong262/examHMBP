"""JustPlay Agent — thu thập WMI local, gửi VPS (không cần domain)."""

from __future__ import annotations

import configparser
import json
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def exe_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    ini_path = exe_dir() / 'justplay_agent.ini'
    if ini_path.is_file():
        cfg.read(ini_path, encoding='utf-8')
    return cfg


def cfg_get(cfg: configparser.ConfigParser, section: str, key: str, default: str = '') -> str:
    if cfg.has_option(section, key):
        return cfg.get(section, key).strip()
    return default


def run_powershell(script: str) -> str:
    if platform.system() != 'Windows':
        return ''
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (result.stdout or '').strip()


def collect_info() -> dict | None:
    serial = run_powershell('(Get-CimInstance Win32_BIOS).SerialNumber')
    if not serial or serial in ('Default string', 'None', ''):
        return None
    hostname = platform.node()
    model = run_powershell('(Get-CimInstance Win32_ComputerSystem).Model')
    cpu = run_powershell('(Get-CimInstance Win32_Processor).Name | Select-Object -First 1')
    ram_raw = run_powershell('(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory')
    try:
        ram_gb = round(int(ram_raw) / (1024 ** 3), 1) if str(ram_raw).isdigit() else ram_raw
    except ValueError:
        ram_gb = ram_raw
    disk = run_powershell(
        '(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | '
        'Select-Object -First 1 @{N=\'Size\';E={[math]::Round($_.Size/1GB,1)}}).Size'
    )
    ip = run_powershell(
        '(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {'
        '$_.IPAddress -notlike \'127.*\' -and $_.IPAddress -notlike \'100.*\' '
        '-and $_.PrefixOrigin -ne \'WellKnown\'} | Select-Object -First 1).IPAddress'
    )
    return {
        'serial': serial,
        'hostname': hostname,
        'model': model,
        'cpu': cpu,
        'ram': str(ram_gb),
        'disk': str(disk),
        'ip': ip,
    }


def _state_path() -> Path:
    return exe_dir() / '.justplay_agent_state.json'


def load_state() -> dict:
    path = _state_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state), encoding='utf-8')


def http_json(url: str, *, method: str = 'GET', payload: dict | None = None, timeout: int = 20) -> dict:
    data = None
    headers = {'Content-Type': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def poll_rescan(*, poll_url: str, api_secret: str, serial: str) -> str | None:
    url = f'{poll_url.rstrip("/")}/?api_secret={api_secret}&serial={serial}'
    try:
        data = http_json(url)
        return data.get('rescan_at')
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return None


def user_fields_from_config(cfg: configparser.ConfigParser) -> dict:
    if not cfg.has_section('user'):
        return {}
    keys = (
        'portal_user_id', 'username', 'full_name', 'email',
        'department', 'install_token',
    )
    out = {}
    for key in keys:
        val = cfg_get(cfg, 'user', key, '')
        if val:
            out[key] = val
    return out


def post_report(*, report_url: str, api_secret: str, info: dict, user_fields: dict | None = None) -> bool:
    payload = {**info, 'api_secret': api_secret}
    if user_fields:
        payload.update(user_fields)
    try:
        data = http_json(report_url, method='POST', payload=payload)
        return data.get('status') == 'success'
    except (urllib.error.URLError, json.JSONDecodeError):
        return False


def normalize_urls(cfg: configparser.ConfigParser) -> tuple[str, str, str]:
    base = cfg_get(cfg, 'portal', 'url', '').rstrip('/')
    report = cfg_get(cfg, 'portal', 'report_url', '')
    poll = cfg_get(cfg, 'portal', 'poll_url', '')
    secret = cfg_get(cfg, 'portal', 'secret', '')

    if not report:
        if base.endswith('/thiet-bi/api/agent-report'):
            report = base + '/'
        elif base.endswith('/thiet-bi'):
            report = f'{base}/api/agent-report/'
        elif base:
            report = f'{base}/thiet-bi/api/agent-report/'
    if not poll:
        poll_base = report.replace('/api/agent-report/', '').replace('/api/agent-report', '')
        poll = f'{poll_base}/api/agent-poll/'

    return report, poll, secret
