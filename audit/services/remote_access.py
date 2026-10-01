"""Đường NAS Portal: VPN site-to-site (IPsec Fortigate VPS <-> văn phòng).

DSM / rclone / LDAP / SSH backup đều trỏ IP LAN của NAS. Trạng thái đọc từ host;
áp dụng lại cấu hình chạy script trên PID 1.
"""

from __future__ import annotations

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

NAS_LAN_HOST_DEFAULT = '192.168.40.252'


def fortigate_wan_ip() -> str:
    return (getattr(settings, 'FORTIGATE_WAN_IP', None) or os.getenv('FORTIGATE_WAN_IP') or '14.161.25.119').strip()


def nas_lan_host() -> str:
    return (getattr(settings, 'NAS_LAN_HOST', None) or os.getenv('NAS_LAN_HOST') or NAS_LAN_HOST_DEFAULT).strip()


def _host_root() -> Path:
    return Path(getattr(settings, 'VPS_HOST_ROOT', '/host/root'))


def _host_proc() -> Path:
    return Path(getattr(settings, 'VPS_HOST_PROC', '/host/proc'))


def _script_path() -> str:
    root = (getattr(settings, 'HOST_PROJECT_DIR', None) or os.getenv('HOST_PROJECT_DIR') or '/opt/portaljustplay').rstrip('/')
    return f'{root}/scripts/vps-nas-site-to-site.sh'


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


def nas_dsm_host() -> str:
    return (urlparse(getattr(settings, 'NAS_DSM_URL', '') or '').hostname or '').strip()


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
    lan = nas_lan_host()
    dsm_host = nas_dsm_host()
    host_ok = _host_root().is_dir() and (_host_root() / 'etc').is_dir()
    return {
        'fortigate_wan': fortigate_wan_ip(),
        'nas_lan_host': lan,
        'nas_lan_url': f'https://{lan}:5556',
        'nas_lan_ok': _tcp_ok(lan, 5556) or _tcp_ok(lan, 445),
        'nas_dsm_host': dsm_host,
        'dsm_on_lan': dsm_host == lan,
        'tailscale_on': _tailscaled_running(),
        'host_ok': host_ok,
        'docker_ok': docker_available(),
        'script': _script_path(),
    }


def apply_site_to_site(*, disable_tailscale: bool = False) -> dict:
    current = remote_access_status()
    if not current['nas_lan_ok']:
        raise VpsMonitorError(
            f'NAS LAN {current["nas_lan_host"]} chưa thông qua VPN site-to-site (445/5556). '
            'Kiểm tra tunnel IPsec trên Fortigate và VPS.'
        )
    result = docker_run_host_script(
        _script_path(),
        'apply',
        timeout=180.0,
        env={
            'FORTIGATE_WAN_IP': fortigate_wan_ip(),
            'NAS_LAN_HOST': nas_lan_host(),
            'DISABLE_TAILSCALE': '1' if disable_tailscale else '0',
            'HOST_PROJECT_DIR': (
                getattr(settings, 'HOST_PROJECT_DIR', None) or os.getenv('HOST_PROJECT_DIR') or '/opt/portaljustplay'
            ),
        },
    )
    after = remote_access_status()
    return {
        'output': result.get('output') or '',
        'tailscale_on': after['tailscale_on'],
        'dsm_on_lan': after['dsm_on_lan'],
    }
