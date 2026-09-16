"""Công tắc đường NAS Portal: Fortinet IPsec (LAN) <-> Tailscale.

Tailscale daemon không tắt. Trạng thái đọc từ host; đổi mode chạy script trên PID 1.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

from audit.services.vps_monitor import (
    VpsMonitorError,
    docker_available,
    docker_run_host_script,
)

MODES = ('fortinet', 'tailscale')
TAILSCALE_CIDR = '100.64.0.0/10'
NAS_LAN_HOST_DEFAULT = '192.168.40.252'
NAS_TS_HOST_DEFAULT = '100.90.91.74'


def fortigate_wan_ip() -> str:
    return (getattr(settings, 'FORTIGATE_WAN_IP', None) or os.getenv('FORTIGATE_WAN_IP') or '14.161.25.119').strip()


def nas_lan_host() -> str:
    return (getattr(settings, 'NAS_LAN_HOST', None) or os.getenv('NAS_LAN_HOST') or NAS_LAN_HOST_DEFAULT).strip()


def nas_ts_host() -> str:
    return (getattr(settings, 'NAS_TS_HOST', None) or os.getenv('NAS_TS_HOST') or NAS_TS_HOST_DEFAULT).strip()


def _host_root() -> Path:
    return Path(getattr(settings, 'VPS_HOST_ROOT', '/host/root'))


def _host_proc() -> Path:
    return Path(getattr(settings, 'VPS_HOST_PROC', '/host/proc'))


def _script_path() -> str:
    root = (getattr(settings, 'HOST_PROJECT_DIR', None) or os.getenv('HOST_PROJECT_DIR') or '/opt/portaljustplay').rstrip('/')
    return f'{root}/scripts/vps-remote-access-mode.sh'


def _tailscaled_running() -> bool:
    proc = _host_proc()
    if not proc.is_dir():
        return False
    try:
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            comm = entry / 'comm'
            if not comm.is_file():
                continue
            if comm.read_text(encoding='utf-8', errors='replace').strip() == 'tailscaled':
                return True
    except OSError:
        return False
    return False


def _mode_file() -> str:
    path = _host_root() / 'etc/portaljustplay/remote-access.mode'
    if not path.is_file():
        return ''
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip().lower()
    except OSError:
        return ''


def infer_mode(*, file_mode: str, nas_on_tailscale: bool) -> str:
    if file_mode in MODES:
        return file_mode
    return 'tailscale' if nas_on_tailscale else 'fortinet'


def _nas_host_on_tailscale() -> bool:
    host = (urlparse(getattr(settings, 'NAS_DSM_URL', '') or '').hostname or '').strip()
    if not host:
        return False
    try:
        return ipaddress.ip_address(host) in ipaddress.ip_network(TAILSCALE_CIDR)
    except ValueError:
        return host.endswith('.ts.net') or host.startswith('100.')


def _tcp_ok(host: str, port: int, timeout: float = 3.0) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def remote_access_status() -> dict:
    wan = fortigate_wan_ip()
    lan = nas_lan_host()
    ts_host = nas_ts_host()
    ts_on = _tailscaled_running()
    file_mode = _mode_file()
    nas_on_ts = _nas_host_on_tailscale()
    mode = infer_mode(file_mode=file_mode, nas_on_tailscale=nas_on_ts)
    mismatch = (file_mode == 'fortinet' and nas_on_ts) or (file_mode == 'tailscale' and not nas_on_ts)
    host_ok = _host_root().is_dir() and (_host_root() / 'etc').is_dir()
    lan_ok = _tcp_ok(lan, 5556) or _tcp_ok(lan, 445)
    return {
        'mode': mode,
        'mode_file': file_mode or None,
        'tailscale_on': ts_on,
        'mismatch': mismatch,
        'fortigate_wan': wan,
        'tailscale_cidr': TAILSCALE_CIDR,
        'host_ok': host_ok,
        'docker_ok': docker_available(),
        'script': _script_path(),
        'nas_on_tailscale': nas_on_ts,
        'nas_lan_host': lan,
        'nas_ts_host': ts_host,
        'nas_lan_url': f'https://{lan}:5556',
        'nas_lan_ok': lan_ok,
    }


def apply_remote_access_mode(mode: str) -> dict:
    mode = (mode or '').strip().lower()
    if mode not in MODES:
        raise VpsMonitorError('Chế độ không hợp lệ. Chọn fortinet hoặc tailscale.')
    current = remote_access_status()
    already = (
        (mode == 'fortinet' and not current['nas_on_tailscale'] and current['mode_file'] == 'fortinet')
        or (mode == 'tailscale' and current['nas_on_tailscale'] and current['mode'] == 'tailscale')
    )
    if already:
        return {
            'mode': mode,
            'unchanged': True,
            'output': 'Đang ở chế độ này rồi.',
        }
    if mode == 'fortinet' and not current['nas_lan_ok']:
        raise VpsMonitorError(
            f'NAS LAN {current["nas_lan_host"]} chưa thông qua IPsec. '
            'Không swap. Tailscale giữ nguyên.'
        )
    result = docker_run_host_script(
        _script_path(),
        mode,
        timeout=180.0,
        env={
            'FORTIGATE_WAN_IP': fortigate_wan_ip(),
            'NAS_LAN_HOST': nas_lan_host(),
            'NAS_TS_HOST': nas_ts_host(),
            'HOST_PROJECT_DIR': (
                getattr(settings, 'HOST_PROJECT_DIR', None) or os.getenv('HOST_PROJECT_DIR') or '/opt/portaljustplay'
            ),
        },
    )
    after = remote_access_status()
    return {
        'mode': after['mode'],
        'unchanged': False,
        'output': result.get('output') or '',
        'tailscale_on': after['tailscale_on'],
        'nas_on_tailscale': after['nas_on_tailscale'],
    }
