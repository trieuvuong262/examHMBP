"""Giám sát tài nguyên NAS Synology (RAM/CPU/ổ đĩa) qua DSM API và rclone."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import requests
from django.conf import settings

from audit.portal_backup import backup_rclone_base
from nas_storage.nas_paths import default_nas_rclone_remote, nas_is_available, nas_mount_root, rclone_listing_available


class NasMonitorError(Exception):
    pass


_dsm_sid: str | None = None
_dsm_sid_expires_at: float = 0.0


def _format_bytes(value: int | float | None) -> str:
    if value is None:
        return '—'
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    n = float(value)
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    if i == 0:
        return f'{int(n)} {units[i]}'
    return f'{n:.1f} {units[i]}'


def _rclone_env() -> dict:
    env = os.environ.copy()
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and os.path.isfile(config):
        env['RCLONE_CONFIG'] = config
    return env


def _run_rclone(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ['rclone', *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_rclone_env(),
    )


def _read_nas_cred() -> tuple[str, str]:
    """Đọc user/pass NAS từ file cred trên VPS (cùng nguồn rclone)."""
    path = Path(getattr(settings, 'NAS_DSM_CRED_FILE', '/root/.nas-cred'))
    if not path.is_file():
        return '', ''
    username = ''
    password = ''
    try:
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line.startswith('username='):
                username = line.split('=', 1)[1].strip()
            elif line.startswith('password='):
                password = line.split('=', 1)[1].strip()
    except OSError:
        return '', ''
    return username, password


def _dsm_credentials() -> tuple[str, str]:
    account = (getattr(settings, 'NAS_DSM_ACCOUNT', '') or '').strip()
    password = (getattr(settings, 'NAS_DSM_PASSWORD', '') or '').strip()
    cred_user, cred_pass = _read_nas_cred()
    if not account:
        account = cred_user or 'tailscale-justplay'
    if not password:
        password = cred_pass
    return account, password


def dsm_configured() -> bool:
    url = (getattr(settings, 'NAS_DSM_URL', '') or '').strip()
    account, password = _dsm_credentials()
    return bool(url and account and password)


def _dsm_base_url() -> str:
    url = (getattr(settings, 'NAS_DSM_URL', '') or '').strip().rstrip('/')
    if not url:
        raise NasMonitorError('Chưa cấu hình NAS_DSM_URL.')
    return url


def _dsm_verify_ssl() -> bool:
    return bool(getattr(settings, 'NAS_DSM_VERIFY_SSL', False))


def _dsm_request(api: str, method: str, *, version: int = 1, params: dict | None = None, timeout: int = 10) -> dict:
    global _dsm_sid, _dsm_sid_expires_at

    if not dsm_configured():
        raise NasMonitorError('Chưa cấu hình DSM (NAS_DSM_URL hoặc mật khẩu tailscale-justplay).')

    account, password = _dsm_credentials()
    now = time.time()
    if not _dsm_sid or now >= _dsm_sid_expires_at:
        login_params = {
            'api': 'SYNO.API.Auth',
            'version': '7',
            'method': 'login',
            'account': account,
            'passwd': password,
            'session': 'PortalNasMonitor',
            'format': 'sid',
        }
        try:
            resp = requests.get(
                f'{_dsm_base_url()}/webapi/auth.cgi',
                params=login_params,
                timeout=timeout,
                verify=_dsm_verify_ssl(),
            )
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise NasMonitorError(f'Không đăng nhập được DSM: {exc}') from exc

        if not payload.get('success'):
            login_params['version'] = '6'
            try:
                resp = requests.get(
                    f'{_dsm_base_url()}/webapi/auth.cgi',
                    params=login_params,
                    timeout=timeout,
                    verify=_dsm_verify_ssl(),
                )
                payload = resp.json()
            except (requests.RequestException, ValueError) as exc:
                raise NasMonitorError(f'Không đăng nhập được DSM: {exc}') from exc

        if not payload.get('success'):
            code = (payload.get('error') or {}).get('code')
            raise NasMonitorError(f'Đăng nhập DSM thất bại (mã {code}).')

        _dsm_sid = payload['data']['sid']
        _dsm_sid_expires_at = now + 25 * 60

    query = {
        'api': api,
        'version': str(version),
        'method': method,
        '_sid': _dsm_sid,
    }
    if params:
        query.update(params)

    try:
        resp = requests.get(
            f'{_dsm_base_url()}/webapi/entry.cgi',
            params=query,
            timeout=timeout,
            verify=_dsm_verify_ssl(),
        )
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise NasMonitorError(f'Lỗi gọi DSM API ({api}): {exc}') from exc

    if not payload.get('success'):
        code = (payload.get('error') or {}).get('code')
        if code in (119, 105):  # session timeout / invalid
            _dsm_sid = None
            _dsm_sid_expires_at = 0.0
        raise NasMonitorError(f'DSM API {api} thất bại (mã {code}).')

    return payload.get('data') or {}


def _mb_to_bytes(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value) * 1024 * 1024)
    except (TypeError, ValueError):
        return None


def _read_dsm_utilization() -> dict:
    data = _dsm_request('SYNO.Core.System.Utilization', 'get')
    cpu = data.get('cpu') or {}
    memory = data.get('memory') or {}

    cpu_load = cpu.get('load') or cpu.get('user_load')
    if cpu_load is None:
        user_load = float(cpu.get('user_load') or 0)
        system_load = float(cpu.get('system_load') or 0)
        other_load = float(cpu.get('other_load') or 0)
        cpu_load = user_load + system_load + other_load

    mem_total = _mb_to_bytes(memory.get('total_real') or memory.get('memory_size'))
    mem_avail = _mb_to_bytes(memory.get('avail_real'))
    mem_used = (mem_total - mem_avail) if mem_total is not None and mem_avail is not None else None
    mem_pct = round(mem_used / mem_total * 100, 1) if mem_total and mem_used is not None else None

    return {
        'cpu_percent': round(float(cpu_load), 1) if cpu_load is not None else None,
        'ram': {
            'total_bytes': mem_total,
            'used_bytes': mem_used,
            'available_bytes': mem_avail,
            'used_percent': mem_pct,
            'display': f'{_format_bytes(mem_used)} / {_format_bytes(mem_total)}',
        },
    }


def _read_dsm_system_info() -> dict:
    try:
        data = _dsm_request('SYNO.Core.System', 'info', version=3)
    except NasMonitorError:
        data = _dsm_request('SYNO.Core.System', 'info', version=1)
    return {
        'model': data.get('model') or data.get('model_string'),
        'version': data.get('version_string') or data.get('firmware_ver'),
        'hostname': data.get('hostname') or data.get('server_name'),
        'serial': data.get('serial'),
    }


def _read_dsm_storage() -> list[dict]:
    try:
        data = _dsm_request('SYNO.Storage.CGI.Storage', 'load_info', version=1, timeout=15)
    except NasMonitorError:
        return []

    volumes: list[dict] = []
    for vol in data.get('volumes') or []:
        total = vol.get('size') or vol.get('total_size')
        used = vol.get('used') or vol.get('used_size')
        if isinstance(total, dict):
            total = total.get('total')
            used = used or total.get('used') if isinstance(used, dict) else used
        try:
            total_b = int(total)
            used_b = int(used) if used is not None else None
        except (TypeError, ValueError):
            continue
        pct = round(used_b / total_b * 100, 1) if total_b and used_b is not None else None
        volumes.append({
            'id': vol.get('id') or vol.get('volume_id'),
            'name': vol.get('display_name') or vol.get('vol_path') or vol.get('id'),
            'status': vol.get('status') or vol.get('vol_status'),
            'total_bytes': total_b,
            'used_bytes': used_b,
            'used_percent': pct,
            'display': f'{_format_bytes(used_b)} / {_format_bytes(total_b)}',
        })
    return volumes


def collect_nas_processes(*, limit: int = 25) -> list[dict]:
    if not dsm_configured():
        return []
    try:
        data = _dsm_request('SYNO.Core.System.Process', 'list', version=1, timeout=15)
    except NasMonitorError:
        return []

    rows: list[dict] = []
    for proc in data.get('process') or data.get('processes') or []:
        if isinstance(proc, dict):
            name = proc.get('name') or proc.get('command') or proc.get('process_name') or '—'
            try:
                pid = int(proc.get('pid') or 0)
            except (TypeError, ValueError):
                pid = 0
            mem_bytes = proc.get('memory') or proc.get('memory_usage') or proc.get('rss')
            if isinstance(mem_bytes, (int, float)) and mem_bytes < 10_000_000:
                mem_bytes = _mb_to_bytes(mem_bytes)
            try:
                mem_bytes = int(mem_bytes) if mem_bytes is not None else None
            except (TypeError, ValueError):
                mem_bytes = None
            cpu_pct = proc.get('cpu') or proc.get('cpu_usage')
            mem_pct = proc.get('memory_percent') or proc.get('mem')
            rows.append({
                'pid': pid,
                'name': str(name)[:64],
                'cpu_percent': round(float(cpu_pct), 1) if cpu_pct is not None else None,
                'memory_percent': round(float(mem_pct), 1) if mem_pct is not None else None,
                'memory_bytes': mem_bytes,
            })
    rows.sort(key=lambda row: row.get('memory_bytes') or 0, reverse=True)
    return rows[:limit]


def _rclone_about(remote: str) -> dict | None:
    if not rclone_listing_available():
        return None
    proc = _run_rclone(['about', remote, '--json'], timeout=45)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    total = data.get('total')
    used = data.get('used')
    free = data.get('free')
    if total is None:
        return None
    used = used if used is not None else max(0, int(total) - int(free or 0))
    pct = round(used / total * 100, 1) if total else None
    return {
        'total_bytes': int(total),
        'used_bytes': int(used),
        'free_bytes': int(free) if free is not None else None,
        'used_percent': pct,
        'display': f'{_format_bytes(used)} / {_format_bytes(total)}',
    }


def _list_shares() -> list[dict]:
    if not rclone_listing_available():
        return []
    remote = default_nas_rclone_remote()
    proc = _run_rclone(['lsd', remote, '--json'], timeout=30)
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        entries = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    shares: list[dict] = []
    for entry in entries:
        name = entry.get('Name') or entry.get('name') or entry.get('Path')
        if not name:
            continue
        share_remote = f'{remote}{name}' if remote.endswith(':') else f'{remote.rstrip("/")}/{name}'
        shares.append({
            'name': name,
            'remote': share_remote,
            'total_bytes': None,
            'used_bytes': None,
            'used_percent': None,
            'display': '—',
        })
    shares.sort(key=lambda row: row['name'].lower())
    return shares


def collect_nas_metrics() -> dict:
    rclone_ok = rclone_listing_available()
    mount_ok = nas_is_available()
    dsm_ok = dsm_configured()

    metrics: dict = {
        'hostname': None,
        'model': None,
        'version': None,
        'rclone_available': rclone_ok,
        'mount_available': mount_ok,
        'dsm_available': dsm_ok,
        'collected_at': time.time(),
        'ram': {},
        'cpu': {'percent': None, 'cores': None, 'loadavg': {}},
        'disk': None,
        'volumes': [],
        'shares': [],
        'backup': {},
        'processes': [],
        'error': None,
    }

    if dsm_ok:
        try:
            info = _read_dsm_system_info()
            metrics['hostname'] = info.get('hostname')
            metrics['model'] = info.get('model')
            metrics['version'] = info.get('version')
        except NasMonitorError as exc:
            metrics['error'] = str(exc)

        try:
            util = _read_dsm_utilization()
            metrics['cpu']['percent'] = util.get('cpu_percent')
            metrics['ram'] = util.get('ram') or {}
        except NasMonitorError as exc:
            if not metrics['error']:
                metrics['error'] = str(exc)

        try:
            metrics['volumes'] = _read_dsm_storage()
        except NasMonitorError:
            pass

        try:
            metrics['processes'] = collect_nas_processes()
        except NasMonitorError:
            metrics['processes'] = []

    if rclone_ok:
        root_remote = default_nas_rclone_remote()
        root_about = _rclone_about(root_remote)
        if root_about:
            metrics['disk'] = {
                'path': root_remote,
                **root_about,
            }
        try:
            metrics['shares'] = _list_shares()
        except OSError:
            metrics['shares'] = []

        backup_remote = backup_rclone_base()
        backup_about = _rclone_about(backup_remote)
        metrics['backup'] = {
            'remote': backup_remote,
            **(backup_about or {}),
        }

    if metrics['volumes'] and not metrics.get('disk'):
        primary = metrics['volumes'][0]
        metrics['disk'] = {
            'path': primary.get('name') or 'volume',
            'total_bytes': primary.get('total_bytes'),
            'used_bytes': primary.get('used_bytes'),
            'used_percent': primary.get('used_percent'),
            'display': primary.get('display'),
        }

    return metrics
