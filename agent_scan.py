"""Agent quét WMI trên Windows — báo cáo thiết bị về Portal JustPlay (1 máy)."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    env_path = ROOT / 'scan_relay.env'
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        pass


_load_dotenv()

SERVER_URL = os.getenv(
    'EQUIPMENT_RELAY_URL',
    os.getenv('PORTAL_PUBLIC_BASE_URL', 'http://127.0.0.1:8000').rstrip('/') + '/thiet-bi/api/agent-report/',
)
if not SERVER_URL.endswith('/thiet-bi/api/agent-report/') and not SERVER_URL.endswith('/thiet-bi/api/agent-report'):
    base = SERVER_URL.rstrip('/')
    if base.endswith('/thiet-bi'):
        SERVER_URL = f'{base}/api/agent-report/'
    elif not base.endswith('agent-report'):
        SERVER_URL = f'{base}/thiet-bi/api/agent-report/'

API_SECRET = os.getenv('EQUIPMENT_AGENT_SECRET', '')


def run_powershell(script: str) -> str:
    if platform.system() != 'Windows':
        return ''
    cmd = ['powershell', '-NoProfile', '-Command', script]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return (result.stdout or '').strip()


def collect_info() -> dict:
    serial = run_powershell('(Get-CimInstance Win32_BIOS).SerialNumber')
    hostname = platform.node()
    model = run_powershell('(Get-CimInstance Win32_ComputerSystem).Model')
    cpu = run_powershell('(Get-CimInstance Win32_Processor).Name | Select-Object -First 1')
    ram = run_powershell('(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory')
    try:
        ram_gb = round(int(ram) / (1024 ** 3), 1) if ram.isdigit() else ram
    except ValueError:
        ram_gb = ram
    disk = run_powershell(
        '(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | '
        'Select-Object -First 1 @{N=\'Size\';E={[math]::Round($_.Size/1GB,1)}}).Size'
    )
    ip = run_powershell(
        '(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike \'127.*\' '
        '-and $_.PrefixOrigin -ne \'WellKnown\'} | Select-Object -First 1).IPAddress'
    )
    return {
        'api_secret': API_SECRET,
        'serial': serial,
        'hostname': hostname,
        'model': model,
        'cpu': cpu,
        'ram': str(ram_gb),
        'disk': disk,
        'ip': ip,
    }


def post_report(payload: dict) -> None:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        SERVER_URL,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(resp.read().decode('utf-8'))


def main() -> int:
    if not API_SECRET:
        print('Thiếu EQUIPMENT_AGENT_SECRET — cấu hình trong scan_relay.env.', file=sys.stderr)
        return 1
    payload = collect_info()
    if not payload.get('serial'):
        print('Không đọc được serial.', file=sys.stderr)
        return 1
    try:
        post_report(payload)
    except urllib.error.URLError as exc:
        print(f'Lỗi gửi báo cáo: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
