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


def _sanitize_dsm_error(exc: Exception) -> str:
    msg = str(exc)
    if 'passwd=' in msg:
        import re
        msg = re.sub(r'passwd=[^&\s\'"]+', 'passwd=***', msg)
    if 'Connection refused' in msg or 'Errno 111' in msg:
        base = _dsm_base_url() if (getattr(settings, 'NAS_DSM_URL', '') or '').strip() else 'https://NAS:5556'
        return (
            f'Không kết nối được DSM tại {base} (connection refused). '
            'SMB/rclone vẫn chạy được nhưng cổng HTTPS DSM có thể chưa mở trên IP Tailscale. '
            'Trên Synology: Control Panel → Login Portal → DSM (ghi cổng HTTPS), '
            'Security → Firewall → cho phép cổng đó từ dải Tailscale 100.64.0.0/10.'
        )
    if 'Failed to establish a new connection' in msg or 'Max retries exceeded' in msg:
        return (
            'Không kết nối được NAS qua DSM API từ container Portal. '
            'Kiểm tra NAS_DSM_URL, Tailscale và firewall Synology.'
        )
    return f'Không đăng nhập được DSM: {msg}'


def _dsm_login(*, account: str, password: str, version: str, timeout: int) -> dict:
    login_params = {
        'api': 'SYNO.API.Auth',
        'version': version,
        'method': 'login',
        'account': account,
        'passwd': password,
        'session': 'PortalNasMonitor',
        'format': 'sid',
    }
    resp = requests.post(
        f'{_dsm_base_url()}/webapi/auth.cgi',
        data=login_params,
        timeout=timeout,
        verify=_dsm_verify_ssl(),
    )
    return resp.json()


def _dsm_request(api: str, method: str, *, version: int = 1, params: dict | None = None, timeout: int = 10) -> dict:
    global _dsm_sid, _dsm_sid_expires_at

    if not dsm_configured():
        raise NasMonitorError('Chưa cấu hình DSM (NAS_DSM_URL hoặc mật khẩu tailscale-justplay).')

    account, password = _dsm_credentials()
    now = time.time()
    if not _dsm_sid or now >= _dsm_sid_expires_at:
        try:
            payload = _dsm_login(account=account, password=password, version='7', timeout=timeout)
        except (requests.RequestException, ValueError) as exc:
            raise NasMonitorError(_sanitize_dsm_error(exc)) from exc

        if not payload.get('success'):
            try:
                payload = _dsm_login(account=account, password=password, version='6', timeout=timeout)
            except (requests.RequestException, ValueError) as exc:
                raise NasMonitorError(_sanitize_dsm_error(exc)) from exc

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
        raise NasMonitorError(_sanitize_dsm_error(exc)) from exc

    if not payload.get('success'):
        code = (payload.get('error') or {}).get('code')
        if code in (119, 105):  # session timeout / invalid
            _dsm_sid = None
            _dsm_sid_expires_at = 0.0
        raise NasMonitorError(f'DSM API {api} thất bại (mã {code}).')

    return payload.get('data') or {}


def _volume_row(
    *,
    name: str,
    status,
    total_b: int | None,
    used_b: int | None,
    vol_id=None,
) -> dict | None:
    if not name or not total_b:
        return None
    if used_b is None and total_b is not None:
        used_b = 0
    pct = round(used_b / total_b * 100, 1) if total_b and used_b is not None else None
    return {
        'id': vol_id,
        'name': name,
        'status': status,
        'total_bytes': total_b,
        'used_bytes': used_b,
        'used_percent': pct,
        'display': f'{_format_bytes(used_b)} / {_format_bytes(total_b)}',
    }


def _volume_from_storage_api(vol: dict) -> dict | None:
    total_b = vol.get('size_total_byte') or vol.get('size_total')
    free_b = vol.get('size_free_byte') or vol.get('size_free')
    try:
        total_b = int(total_b) if total_b is not None else None
        free_b = int(free_b) if free_b is not None else None
    except (TypeError, ValueError):
        total_b = None
        free_b = None
    if total_b is None:
        size = vol.get('size') or {}
        if isinstance(size, dict):
            try:
                total_b = int(size.get('total')) if size.get('total') is not None else None
                used_raw = size.get('used')
                used_b = int(used_raw) if used_raw is not None else None
            except (TypeError, ValueError):
                total_b = None
                used_b = None
        else:
            try:
                total_b = int(vol.get('total_size') or size or 0) or None
                used_b = int(vol.get('used_size') or vol.get('used') or 0)
            except (TypeError, ValueError):
                total_b = None
                used_b = None
    else:
        used_b = (total_b - free_b) if free_b is not None else vol.get('used_size') or vol.get('used')
        try:
            used_b = int(used_b) if used_b is not None else None
        except (TypeError, ValueError):
            used_b = None
    name = (
        vol.get('display_name')
        or vol.get('volume_path')
        or vol.get('vol_path')
        or vol.get('id')
    )
    vol_path = vol.get('volume_path') or vol.get('vol_path') or ''
    row = _volume_row(
        name=str(name),
        status=vol.get('status') or vol.get('vol_status'),
        total_b=total_b,
        used_b=used_b,
        vol_id=vol.get('volume_id') or vol.get('id'),
    )
    if row and vol_path:
        row['vol_path'] = vol_path
    return row


def _read_dsm_volumes() -> list[dict]:
    volumes: list[dict] = []
    if not dsm_configured():
        return volumes

    try:
        data = _dsm_request(
            'SYNO.Core.Storage.Volume',
            'list',
            version=1,
            params={'limit': '-1', 'offset': '0', 'location': 'internal'},
            timeout=15,
        )
        for vol in data.get('volumes') or []:
            row = _volume_from_storage_api(vol)
            if row:
                volumes.append(row)
    except NasMonitorError:
        pass

    if not volumes:
        try:
            data = _dsm_request('SYNO.Storage.CGI.Storage', 'load_info', version=1, timeout=15)
            for vol in data.get('volumes') or []:
                row = _volume_from_storage_api(vol)
                if row:
                    volumes.append(row)
        except NasMonitorError:
            pass

    return volumes


def _share_row(*, name: str, total_b: int | None, used_b: int | None, remote: str = '') -> dict:
    pct = round(used_b / total_b * 100, 1) if total_b and used_b is not None else None
    display = f'{_format_bytes(used_b)} / {_format_bytes(total_b)}' if total_b else '—'
    return {
        'name': name,
        'remote': remote,
        'total_bytes': total_b,
        'used_bytes': used_b,
        'used_percent': pct,
        'display': display,
    }


def _read_dsm_filestation_shares() -> list[dict]:
    data = _dsm_request(
        'SYNO.FileStation.List',
        'list_share',
        version=2,
        params={'additional': '["volume_status"]'},
        timeout=15,
    )
    rows: list[dict] = []
    for share in data.get('shares') or []:
        name = share.get('name')
        if not name:
            continue
        vs = (share.get('additional') or {}).get('volume_status') or {}
        try:
            total_b = int(vs.get('totalspace') or vs.get('total_space') or 0) or None
            free_b = int(vs.get('freespace') or vs.get('free_space') or 0)
            used_b = (total_b - free_b) if total_b is not None else None
        except (TypeError, ValueError):
            total_b = None
            used_b = None
        rows.append(_share_row(name=name, total_b=total_b, used_b=used_b, remote=share.get('path') or ''))
    rows.sort(key=lambda row: row['name'].lower())
    return rows


def _read_dsm_core_shares(volumes: list[dict] | None = None) -> list[dict]:
    data = _dsm_request(
        'SYNO.Core.Share',
        'list',
        version=1,
        params={'shareType': 'all', 'additional': '["real_path"]'},
        timeout=15,
    )
    vol_by_path = {}
    for vol in volumes or []:
        for key in (vol.get('vol_path'), vol.get('name')):
            if key and str(key).startswith('/volume'):
                vol_by_path[str(key)] = vol
    rows: list[dict] = []
    for share in data.get('shares') or []:
        name = share.get('name')
        if not name:
            continue
        vol_path = share.get('vol_path') or ''
        vol = vol_by_path.get(vol_path) or {}
        rows.append(_share_row(
            name=name,
            total_b=vol.get('total_bytes'),
            used_b=vol.get('used_bytes'),
            remote=(share.get('additional') or {}).get('real_path') or vol_path,
        ))
    rows.sort(key=lambda row: row['name'].lower())
    return rows


def _list_shares_from_mount() -> list[dict]:
    root = nas_mount_root()
    if not root.is_dir():
        return []
    rows: list[dict] = []
    try:
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            rows.append(_share_row(name=entry.name, total_b=None, used_b=None, remote=str(entry)))
    except OSError:
        return []
    return rows


def _list_shares_from_rclone() -> list[dict]:
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
        shares.append(_share_row(name=name, total_b=None, used_b=None, remote=share_remote))
    shares.sort(key=lambda row: row['name'].lower())
    return shares


def _collect_shares(*, volumes: list[dict] | None = None) -> list[dict]:
    if dsm_configured():
        for loader in (
            lambda: _read_dsm_filestation_shares(),
            lambda: _read_dsm_core_shares(volumes),
        ):
            try:
                rows = loader()
                if rows:
                    return rows
            except NasMonitorError:
                continue

    rows = _list_shares_from_rclone()
    if rows:
        return rows
    return _list_shares_from_mount()


def _kb_to_bytes(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value) * 1024)
    except (TypeError, ValueError):
        return None


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

    mem_total = _kb_to_bytes(memory.get('total_real') or memory.get('memory_size'))
    mem_avail = _kb_to_bytes(memory.get('avail_real'))
    mem_used = (mem_total - mem_avail) if mem_total is not None and mem_avail is not None else None
    mem_pct = memory.get('real_usage')
    if mem_pct is not None:
        try:
            mem_pct = round(float(mem_pct), 1)
        except (TypeError, ValueError):
            mem_pct = round(mem_used / mem_total * 100, 1) if mem_total and mem_used is not None else None
    else:
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
        'network': data.get('network') if isinstance(data.get('network'), list) else [],
        'disk_io': data.get('disk') if isinstance(data.get('disk'), dict) else {},
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


def _dsm_try_requests(calls: list[tuple[str, str, int, dict | None]]) -> dict:
    for api, method, version, params in calls:
        try:
            return _dsm_request(api, method, version=version, params=params, timeout=15)
        except NasMonitorError:
            continue
    return {}


def _read_dsm_widget_system_health() -> dict:
    data = _dsm_try_requests([
        ('SYNO.Core.System.SystemHealth', 'get', 1, None),
        ('SYNO.Core.System.Status', 'get', 1, None),
    ])
    status = data.get('status') or data.get('system_status') or data.get('health')
    if isinstance(status, dict):
        status = status.get('status') or status.get('value') or status.get('text')
    summary = data.get('summary') or data.get('message') or data.get('overview') or ''
    if isinstance(summary, dict):
        summary = summary.get('text') or summary.get('message') or ''
    return {
        'status': str(status) if status not in (None, '') else '—',
        'temperature': data.get('temperature'),
        'summary': str(summary)[:300] if summary else '',
    }


def _read_dsm_widget_connected_users() -> list[dict]:
    data = _dsm_try_requests([('SYNO.Core.CurrentConnection', 'list', 1, None)])
    items = data.get('items') or data.get('connections') or data.get('users') or []
    rows: list[dict] = []
    for item in items[:25]:
        if not isinstance(item, dict):
            continue
        rows.append({
            'user': item.get('user') or item.get('username') or item.get('name') or '—',
            'ip': item.get('ip') or item.get('from') or item.get('address') or '—',
            'protocol': item.get('protocol') or item.get('type') or item.get('service') or '—',
            'time': item.get('time') or item.get('login_time') or item.get('connected_time') or '—',
        })
    return rows


def _read_dsm_widget_scheduled_tasks() -> list[dict]:
    data = _dsm_try_requests([
        ('SYNO.Core.TaskScheduler', 'list', 3, None),
        ('SYNO.Core.TaskScheduler', 'list', 1, None),
    ])
    rows: list[dict] = []
    for task in (data.get('tasks') or [])[:30]:
        if not isinstance(task, dict):
            continue
        enabled = task.get('enable') if 'enable' in task else task.get('enabled')
        rows.append({
            'name': task.get('name') or '—',
            'type': task.get('type') or task.get('real_owner') or '—',
            'enabled': enabled,
            'next': task.get('next_trigger_time') or task.get('next_run') or '—',
            'last': task.get('last_run_result') or task.get('last_run_time') or '—',
        })
    return rows


def _read_dsm_widget_recent_logs(*, limit: int = 15) -> list[dict]:
    data = _dsm_try_requests([
        ('SYNO.Core.SyslogClient.Status', 'latestlog_get', 1, {'limit': str(limit)}),
        ('SYNO.LogCenter.Client', 'list', 1, {'limit': str(limit), 'offset': '0'}),
    ])
    logs = data.get('logs') or data.get('items') or data.get('log') or []
    rows: list[dict] = []
    for log in logs[:limit]:
        if not isinstance(log, dict):
            continue
        rows.append({
            'time': log.get('time') or log.get('datetime') or log.get('date') or '—',
            'level': log.get('level') or log.get('severity') or '—',
            'message': str(log.get('msg') or log.get('message') or log.get('desc') or '—')[:240],
        })
    return rows


def _read_dsm_widget_backup_tasks() -> list[dict]:
    data = _dsm_try_requests([
        ('SYNO.Backup.Task', 'list', 1, None),
        ('SYNO.HyperBackup.Util', 'list_task', 1, None),
    ])
    tasks = data.get('tasks') or data.get('data') or []
    rows: list[dict] = []
    for task in tasks[:20]:
        if not isinstance(task, dict):
            continue
        rows.append({
            'name': task.get('name') or task.get('task_name') or '—',
            'status': task.get('status') or task.get('state') or '—',
            'last': task.get('last_run_time') or task.get('last_bkp_time') or '—',
        })
    return rows


def _read_dsm_widget_file_changes(*, limit: int = 15) -> list[dict]:
    data = _dsm_try_requests([
        ('SYNO.Finder.FileSharing', 'get_changelog', 1, {'limit': str(limit)}),
        ('SYNO.Core.AuditLog', 'list', 1, {'limit': str(limit), 'offset': '0'}),
    ])
    items = data.get('items') or data.get('logs') or data.get('changelog') or []
    rows: list[dict] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append({
            'time': item.get('time') or item.get('mtime') or item.get('datetime') or '—',
            'user': item.get('user') or item.get('username') or '—',
            'path': str(item.get('path') or item.get('file') or '—')[:120],
            'action': item.get('action') or item.get('type') or '—',
        })
    return rows


def collect_dsm_widgets() -> dict:
    if not dsm_configured():
        return {}
    return {
        'system_health': _read_dsm_widget_system_health(),
        'connected_users': _read_dsm_widget_connected_users(),
        'scheduled_tasks': _read_dsm_widget_scheduled_tasks(),
        'recent_logs': _read_dsm_widget_recent_logs(),
        'backup_tasks': _read_dsm_widget_backup_tasks(),
        'file_changes': _read_dsm_widget_file_changes(),
    }


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
                mem_bytes = _kb_to_bytes(mem_bytes)
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
        'widgets': {},
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
            metrics['volumes'] = _read_dsm_volumes()
        except NasMonitorError:
            metrics['volumes'] = []

        try:
            metrics['processes'] = collect_nas_processes()
        except NasMonitorError:
            metrics['processes'] = []

        try:
            metrics['widgets'] = collect_dsm_widgets()
        except NasMonitorError:
            metrics['widgets'] = {}

    try:
        metrics['shares'] = _collect_shares(volumes=metrics.get('volumes'))
    except OSError:
        metrics['shares'] = []

    if rclone_ok:
        root_remote = default_nas_rclone_remote()
        root_about = _rclone_about(root_remote)
        if root_about:
            metrics['disk'] = {
                'path': root_remote,
                **root_about,
            }

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
