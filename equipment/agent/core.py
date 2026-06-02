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

_BAD_SERIALS = frozenset({
    'default string',
    'to be filled by o.e.m.',
    'system serial number',
    'none',
    '00000000',
    '0123456789',
    '123456789',
})


def is_bad_serial(serial: str | None) -> bool:
    if not serial:
        return True
    text = str(serial).strip()
    if not text:
        return True
    lower = text.lower()
    if lower in _BAD_SERIALS:
        return True
    return any(bad in lower for bad in _BAD_SERIALS)


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
    kwargs: dict = {
        'capture_output': True,
        'text': True,
        'timeout': 45,
    }
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
        **kwargs,
    )
    return (result.stdout or '').strip()


def resolve_serial() -> str:
    """Serial BIOS / bo mạch / UUID — fallback khi OEM de serial mac dinh."""
    queries = (
        '(Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue | Select-Object -First 1).SerialNumber',
        '(Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue | Select-Object -First 1).SerialNumber',
        '(Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue | Select-Object -First 1).UUID',
        "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -ErrorAction SilentlyContinue).MachineGuid",
    )
    for query in queries:
        value = run_powershell(query)
        if not is_bad_serial(value):
            return value.strip()

    try:
        result = subprocess.run(
            ['wmic', 'csproduct', 'get', 'uuid'],
            capture_output=True,
            text=True,
            timeout=30,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}),
        )
        for line in (result.stdout or '').splitlines():
            line = line.strip()
            if line and line.lower() != 'uuid' and not is_bad_serial(line):
                return line
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    hostname = (platform.node() or '').strip()
    if hostname:
        return f'HOST-{hostname.upper()}'
    return ''


def collect_info() -> dict | None:
    serial = resolve_serial()
    if not serial:
        return None
    hostname = platform.node()
    model = run_powershell(
        '(Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).Model'
    )
    cpu = run_powershell(
        '(Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1).Name'
    )
    ram_raw = run_powershell(
        '(Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).TotalPhysicalMemory'
    )
    try:
        ram_gb = round(int(ram_raw) / (1024 ** 3), 1) if str(ram_raw).isdigit() else ram_raw
    except ValueError:
        ram_gb = ram_raw
    disk = run_powershell(
        '(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction SilentlyContinue | '
        'Select-Object -First 1 @{N=\'Size\';E={[math]::Round($_.Size/1GB,1)}}).Size'
    )
    ip = run_powershell(
        '(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {'
        '$_.IPAddress -notlike \'127.*\' -and $_.IPAddress -notlike \'100.*\' '
        '-and $_.PrefixOrigin -ne \'WellKnown\'} | Select-Object -First 1).IPAddress'
    )
    os_caption = run_powershell(
        '(Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption'
    )
    os_build = run_powershell(
        '(Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Version'
    )
    manufacturer = run_powershell(
        '(Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).Manufacturer'
    )
    return {
        'serial': serial,
        'hostname': hostname,
        'model': model,
        'cpu': cpu,
        'ram': str(ram_gb),
        'disk': str(disk),
        'ip': ip,
        'os': os_caption,
        'os_build': os_build,
        'manufacturer': manufacturer,
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
        'department', 'department_id', 'division',
        'job_position', 'job_title', 'employee_code',
        'install_token', 'machine_type',
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
