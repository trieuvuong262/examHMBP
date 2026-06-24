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


def _parse_byte_value(value) -> int | None:
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        for key in ('size', 'used', 'used_space', 'used_size', 'total_size', 'quota_size', 'quota', 'total'):
            parsed = _parse_byte_value(value.get(key))
            if parsed is not None:
                return parsed
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dsm_share_quota_mb_to_bytes(value) -> int | None:
    """DSM share_quota_status v2: quota_value / share_quota_used tính theo MB."""
    if value in (None, '', 0, '0'):
        return None
    try:
        megabytes = float(value)
    except (TypeError, ValueError):
        return None
    if megabytes <= 0:
        return None
    return int(megabytes * 1024 * 1024)


def _parse_dsm_share_quota(share: dict) -> dict | None:
    if not isinstance(share, dict):
        return None
    status = share.get('share_quota_status')
    if status in (None, '', 0, '0', False):
        extra = share.get('additional') or {}
        quota = extra.get('share_quota')
        if isinstance(quota, dict) and quota:
            total_b = _quota_total_bytes(quota)
            used_b = _quota_used_bytes(quota)
            if total_b:
                return {
                    'quota_size': total_b,
                    'used_space': used_b,
                    'free_space': max(0, total_b - used_b) if used_b is not None else None,
                }
        return None
    total_b = _dsm_share_quota_mb_to_bytes(share.get('quota_value'))
    size_b = _dsm_share_quota_mb_to_bytes(share.get('share_quota_used'))
    if total_b is None:
        return None
    free_b = max(0, total_b - size_b) if size_b is not None else None
    return {
        'quota_size': total_b,
        'used_space': size_b,
        'free_space': free_b,
    }


def _share_row(
    *,
    name: str,
    total_b: int | None,
    used_b: int | None,
    free_b: int | None = None,
    remote: str = '',
) -> dict:
    """used_b = Shared Folder Size; total_b = Shared Folder Quota."""
    if free_b is None and total_b is not None and used_b is not None:
        free_b = max(0, total_b - used_b)
    pct = round(used_b / total_b * 100, 1) if total_b and used_b is not None and total_b > 0 else None
    size_display = _format_bytes(used_b) if used_b is not None else '—'
    quota_display = _format_bytes(total_b) if total_b else '—'
    free_display = _format_bytes(free_b) if free_b is not None else '—'
    if used_b is not None and total_b:
        display = f'Size: {size_display} · Quota: {quota_display}'
    elif used_b is not None:
        display = f'Size: {size_display}'
    elif total_b:
        display = f'Quota: {quota_display}'
    else:
        display = '—'
    return {
        'name': name,
        'remote': remote,
        'total_bytes': total_b,
        'used_bytes': used_b,
        'free_bytes': free_b,
        'used_percent': pct,
        'display': display,
        'size_display': size_display,
        'quota_display': quota_display,
        'used_display': size_display,
        'free_display': free_display,
    }


def _read_dsm_share_quotas() -> dict[str, dict]:
    quotas: dict[str, dict] = {}
    try:
        data = _dsm_request(
            'SYNO.Core.Share',
            'list',
            version=1,
            params={'shareType': 'all', 'additional': '["share_quota","real_path"]'},
            timeout=15,
        )
    except NasMonitorError:
        return quotas
    for share in data.get('shares') or []:
        name = share.get('name')
        if not name:
            continue
        quota = _parse_dsm_share_quota(share)
        if quota:
            quotas[name] = quota
        else:
            extra_quota = (share.get('additional') or {}).get('share_quota')
            if isinstance(extra_quota, dict):
                quotas[name] = extra_quota
            elif share.get('share_quota') not in (None, '', 0):
                quotas[name] = {'quota_size': share.get('share_quota')}
    return quotas


def _quota_total_bytes(quota: dict | None) -> int | None:
    if not isinstance(quota, dict):
        return None
    for key in ('quota_size', 'total_space', 'quota', 'total', 'limit'):
        val = _parse_byte_value(quota.get(key))
        if val is not None and val > 0:
            return val
    return None


def _quota_free_bytes(quota: dict | None) -> int | None:
    if not isinstance(quota, dict):
        return None
    for key in ('free_space', 'free', 'available', 'avail'):
        val = _parse_byte_value(quota.get(key))
        if val is not None:
            return val
    total_b = _quota_total_bytes(quota)
    used_b = _quota_used_bytes(quota)
    if total_b is not None and used_b is not None:
        return max(0, total_b - used_b)
    return None


def _quota_used_bytes(quota: dict | None) -> int | None:
    if not isinstance(quota, dict):
        return None
    for key in ('used_space', 'used', 'used_size'):
        val = _parse_byte_value(quota.get(key))
        if val is not None:
            return val
    return None


def _share_list_size_bytes(value) -> int | None:
    """list_share.size / getinfo trên thư mục thường chỉ là metadata (~vài trăm byte), bỏ qua."""
    used_b = _parse_byte_value(value)
    if used_b is None or used_b < 1024 * 1024:
        return None
    return used_b


def _read_dsm_filestation_shares(quota_map: dict[str, dict] | None = None) -> list[dict]:
    quota_map = quota_map if quota_map is not None else _read_dsm_share_quotas()
    data = _dsm_request(
        'SYNO.FileStation.List',
        'list_share',
        version=2,
        params={'additional': '["size","real_path"]', 'limit': '0'},
        timeout=20,
    )
    rows: list[dict] = []
    for share in data.get('shares') or []:
        name = share.get('name')
        if not name:
            continue
        extra = share.get('additional') or {}
        quota = quota_map.get(name) or {}
        used_b = _share_list_size_bytes(extra.get('size'))
        if used_b is None:
            used_b = _quota_used_bytes(quota)
        total_b = _quota_total_bytes(quota)
        free_b = _quota_free_bytes(quota)
        real_path = extra.get('real_path') or ''
        rows.append(_share_row(
            name=name,
            total_b=total_b,
            used_b=used_b,
            free_b=free_b,
            remote=share.get('path') or real_path or f'/{name}',
        ))
    rows.sort(key=lambda item: item['name'].lower())
    return rows


def _read_dsm_core_shares(quota_map: dict[str, dict] | None = None) -> list[dict]:
    quota_map = quota_map if quota_map is not None else _read_dsm_share_quotas()
    data = _dsm_request(
        'SYNO.Core.Share',
        'list',
        version=1,
        params={'shareType': 'all', 'additional': '["share_quota","real_path"]'},
        timeout=15,
    )
    rows: list[dict] = []
    for share in data.get('shares') or []:
        name = share.get('name')
        if not name:
            continue
        extra = share.get('additional') or {}
        quota = quota_map.get(name) or extra.get('share_quota') or {}
        if not isinstance(quota, dict):
            quota = {}
        used_b = _quota_used_bytes(quota)
        total_b = _quota_total_bytes(quota)
        free_b = _quota_free_bytes(quota)
        rows.append(_share_row(
            name=name,
            total_b=total_b,
            used_b=used_b,
            free_b=free_b,
            remote=extra.get('real_path') or share.get('vol_path') or '',
        ))
    rows.sort(key=lambda row: row['name'].lower())
    return rows


def _share_rclone_remote(name: str, remote: str = '') -> str:
    """Chuyển path DSM (/backup) sang remote rclone (synology:backup)."""
    remote_base = default_nas_rclone_remote()
    candidate = (remote or '').strip()
    if candidate and ':' in candidate:
        return candidate
    if candidate and remote_base and candidate.startswith(remote_base.rstrip(':')):
        return candidate
    return f'{remote_base}{name}' if remote_base.endswith(':') else f'{remote_base.rstrip("/")}/{name}'


def _volume_total_bytes_set(volumes: list[dict] | None) -> set[int]:
    totals: set[int] = set()
    for vol in volumes or []:
        total_b = vol.get('total_bytes')
        if isinstance(total_b, int) and total_b > 0:
            totals.add(total_b)
    return totals


MAX_RCLONE_ABOUT_QUOTA_BYTES = 1024 ** 4  # 1 TB — quota share thường nhỏ hơn; pool/volume hay > 1 TB


def _share_quota_from_about(about_total: int | None, volume_totals: set[int]) -> int | None:
    if not about_total or _is_volume_capacity(about_total, volume_totals):
        return None
    if about_total > MAX_RCLONE_ABOUT_QUOTA_BYTES:
        return None
    return about_total


def _is_volume_capacity(total_b: int | None, volume_totals: set[int]) -> bool:
    return bool(total_b and total_b in volume_totals)


def _rclone_size(remote: str, *, timeout: int = 45) -> int | None:
    if not rclone_listing_available():
        return None
    try:
        proc = _run_rclone(['size', remote, '--json'], timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return _parse_byte_value(data.get('bytes'))


def _enrich_shares_from_rclone(
    rows: list[dict],
    *,
    volumes: list[dict] | None = None,
    quota_map: dict[str, dict] | None = None,
    timeout_about: int = 8,
    timeout_size: int = 25,
    deadline: float | None = None,
) -> list[dict]:
    if not rclone_listing_available():
        return rows
    volume_totals = _volume_total_bytes_set(volumes)
    quota_map = quota_map or {}
    for row in rows:
        if deadline is not None and time.monotonic() >= deadline:
            break
        name = row.get('name')
        if not name:
            continue
        dsm_quota = quota_map.get(name) or {}
        dsm_total = _quota_total_bytes(dsm_quota)
        dsm_used = _quota_used_bytes(dsm_quota)
        dsm_free = _quota_free_bytes(dsm_quota)

        share_remote = _share_rclone_remote(name, row.get('remote') or '')
        about = _rclone_about(share_remote, timeout=timeout_about)
        about_total = about.get('total_bytes') if about else None
        about_quota = _share_quota_from_about(about_total, volume_totals)

        if dsm_total:
            total_b = dsm_total
            used_b = dsm_used
            remaining = None
            if deadline is not None:
                remaining = max(3, int(deadline - time.monotonic()))
            if remaining is not None and remaining > 8:
                size_timeout = min(12, remaining - 2)
                folder_size = _rclone_size(share_remote, timeout=size_timeout)
                if folder_size is not None:
                    used_b = folder_size
            free_b = max(0, total_b - used_b) if used_b is not None else dsm_free
        else:
            quota_total = row.get('total_bytes')
            has_share_quota = bool(quota_total or about_quota)
            total_b = quota_total or about_quota
            used_b = row.get('used_bytes')
            free_b = row.get('free_bytes')
            if has_share_quota and about:
                used_b = about.get('used_bytes') or used_b
                if total_b and used_b is not None:
                    free_b = max(0, total_b - used_b)
            elif used_b is None or _is_volume_capacity(total_b, volume_totals):
                remaining = None
                if deadline is not None:
                    remaining = max(3, int(deadline - time.monotonic()))
                if remaining is None or remaining > 3:
                    size_timeout = min(timeout_size, remaining) if remaining else timeout_size
                    used_b = _rclone_size(share_remote, timeout=size_timeout) or used_b
                if used_b is None and about:
                    used_b = about.get('used_bytes')
            if not has_share_quota:
                total_b = None
                free_b = None

        row.update(_share_row(
            name=name,
            total_b=total_b,
            used_b=used_b,
            free_b=free_b,
            remote=share_remote,
        ))
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
    deadline = time.monotonic() + 50
    if dsm_configured():
        quota_map: dict[str, dict] = {}
        try:
            quota_map = _read_dsm_share_quotas()
        except NasMonitorError:
            pass
        for loader in (
            lambda: _read_dsm_filestation_shares(quota_map),
            lambda: _read_dsm_core_shares(quota_map),
        ):
            try:
                rows = loader()
                if rows:
                    return _enrich_shares_from_rclone(rows, volumes=volumes, quota_map=quota_map, deadline=deadline)
            except NasMonitorError:
                continue

    rows = _list_shares_from_rclone()
    if rows:
        return _enrich_shares_from_rclone(rows, volumes=volumes, quota_map={}, deadline=deadline)
    return _list_shares_from_mount()


def _kb_to_bytes(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value) * 1024)
    except (TypeError, ValueError):
        return None


def _dsm_memory_to_bytes(value) -> int | None:
    """DSM Utilization memory fields are usually KB; some firmware reports MB for small values."""
    if value is None:
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    # 128 MB..256 GB expressed as MB fits below ~262144; RAM in KB is usually larger (e.g. 524288 = 512 MB).
    if n < 262144:
        return int(n * 1024 * 1024)
    return int(n * 1024)


def _parse_dsm_memory(memory: dict) -> dict:
    """Map Synology utilization memory object to total/used/available bytes and %.

    DSM Resource Monitor uses physical RAM (memory_size) and real_usage (%).
    total_real/avail_real describe the active pool — not suitable as installed/total RAM.
    """
    mem_total = _dsm_memory_to_bytes(memory.get('memory_size'))
    if mem_total is None:
        mem_total = _dsm_memory_to_bytes(memory.get('total_real'))

    mem_pct = memory.get('real_usage')
    if mem_pct is not None:
        try:
            mem_pct = round(float(mem_pct), 1)
        except (TypeError, ValueError):
            mem_pct = None

    mem_used = None
    if mem_total is not None and mem_pct is not None:
        mem_used = int(mem_total * mem_pct / 100)
    elif mem_total is not None:
        avail_b = _dsm_memory_to_bytes(memory.get('avail_real'))
        if avail_b is not None:
            mem_used = max(0, mem_total - avail_b)

    if mem_pct is None and mem_total and mem_used is not None:
        mem_pct = round(mem_used / mem_total * 100, 1)

    mem_avail = None
    if mem_total is not None and mem_used is not None:
        mem_avail = max(0, mem_total - mem_used)
    else:
        mem_avail = _dsm_memory_to_bytes(memory.get('avail_real'))

    return {
        'total_bytes': mem_total,
        'used_bytes': mem_used,
        'available_bytes': mem_avail,
        'used_percent': mem_pct,
        'display': (
            f'{_format_bytes(mem_used)} / {_format_bytes(mem_total)}'
            if mem_total and mem_used is not None
            else '—'
        ),
        'buffer_bytes': _dsm_memory_to_bytes(memory.get('buffer')),
        'cached_bytes': _dsm_memory_to_bytes(memory.get('cached')),
        'buffer_display': _format_bytes(_dsm_memory_to_bytes(memory.get('buffer'))),
        'cached_display': _format_bytes(_dsm_memory_to_bytes(memory.get('cached'))),
    }


def _mb_to_bytes(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value) * 1024 * 1024)
    except (TypeError, ValueError):
        return None


def _pick_dict(item: dict | None, *keys, default=None):
    if not isinstance(item, dict):
        return default
    for key in keys:
        val = item.get(key)
        if val not in (None, '', []):
            return val
    return default


def _format_dsm_time(value) -> str:
    if value in (None, '', '—', 0, '0'):
        return '—'
    if isinstance(value, str) and not value.isdigit() and (':' in value or '-' in value):
        return value[:19]
    try:
        ts = int(float(value))
        if ts > 1_000_000_000_000:
            ts //= 1000
        if ts > 0:
            return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))
    except (TypeError, ValueError, OSError):
        pass
    return str(value)


def _format_uptime(seconds) -> str:
    if seconds in (None, '', 0, '0'):
        return '—'
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    days, rem = divmod(total, 86400)
    hours, minutes = divmod(rem, 3600)
    minutes //= 60
    parts = []
    if days:
        parts.append(f'{days} ngày')
    if hours:
        parts.append(f'{hours} giờ')
    if minutes or not parts:
        parts.append(f'{minutes} phút')
    return ' '.join(parts)


def _extract_list(data: dict | None, *keys) -> list:
    if not isinstance(data, dict):
        return []
    for key in keys:
        val = data.get(key)
        if isinstance(val, list):
            return val
    return []


def _dsm_try_requests(calls: list[tuple[str, str, int, dict | None]]) -> dict:
    merged: dict = {}
    for api, method, version, params in calls:
        try:
            data = _dsm_request(api, method, version=version, params=params, timeout=15)
        except NasMonitorError:
            continue
        if not isinstance(data, dict):
            continue
        for key, val in data.items():
            if val in (None, '', {}):
                continue
            if key not in merged or merged[key] in (None, '', [], {}):
                merged[key] = val
            elif isinstance(val, list) and isinstance(merged[key], list):
                merged[key] = merged[key] + val
    return merged


def _dsm_collect_items(
    calls: list[tuple[str, str, int, dict | None]],
    *list_keys: str,
) -> list[dict]:
    seen: set = set()
    items: list[dict] = []
    for api, method, version, params in calls:
        try:
            data = _dsm_request(api, method, version=version, params=params, timeout=15)
        except NasMonitorError:
            continue
        for raw in _extract_list(data, *list_keys):
            if not isinstance(raw, dict):
                continue
            uid = (
                raw.get('id'),
                raw.get('session_id'),
                _pick_dict(raw, 'who', 'user', 'username', 'name'),
                _pick_dict(raw, 'from', 'ip', 'address'),
                _pick_dict(raw, 'time', 'datetime', 'mtime'),
                _pick_dict(raw, 'path', 'file'),
            )
            if uid in seen:
                continue
            seen.add(uid)
            items.append(raw)
    return items


def _parse_dsm_cpu_percent(cpu: dict) -> float | None:
    if not isinstance(cpu, dict):
        return None
    for key in ('load', 'total_load', 'cpu_load'):
        val = cpu.get(key)
        if val is not None:
            try:
                pct = float(val)
                if pct > 0:
                    return round(pct, 1)
            except (TypeError, ValueError):
                pass
    try:
        user_load = float(cpu.get('user_load') or 0)
        system_load = float(cpu.get('system_load') or 0)
        other_load = float(cpu.get('other_load') or 0)
        combined = user_load + system_load + other_load
        if combined > 0:
            return round(combined, 1)
    except (TypeError, ValueError):
        pass
    for key in ('1min_load', 'load1', '5min_load', 'load5'):
        val = cpu.get(key)
        if val is not None:
            try:
                return round(float(val), 1)
            except (TypeError, ValueError):
                continue
    return 0.0 if cpu else None


def _read_dsm_utilization() -> dict:
    data = _dsm_request('SYNO.Core.System.Utilization', 'get')
    cpu = data.get('cpu') or {}
    memory = data.get('memory') or {}
    swap = data.get('swap') or memory.get('swap') or {}

    cpu_load = _parse_dsm_cpu_percent(cpu)

    ram = _parse_dsm_memory(memory)

    swap_total = _dsm_memory_to_bytes(swap.get('total') or memory.get('swap_total') or memory.get('total_swap'))
    swap_used = _dsm_memory_to_bytes(swap.get('used') or memory.get('swap_usage'))
    if swap_used is None and swap_total and swap.get('available') is not None:
        swap_avail = _dsm_memory_to_bytes(swap.get('available') or memory.get('avail_swap'))
        if swap_avail is not None:
            swap_used = max(0, swap_total - swap_avail)

    network_rows: list[dict] = []
    for iface in data.get('network') or []:
        if not isinstance(iface, dict):
            continue
        rx = iface.get('rx') or iface.get('rx_bytes') or iface.get('rx_kbyte')
        tx = iface.get('tx') or iface.get('tx_bytes') or iface.get('tx_kbyte')
        if isinstance(rx, (int, float)) and rx < 10_000_000:
            rx = int(rx * 1024)
        if isinstance(tx, (int, float)) and tx < 10_000_000:
            tx = int(tx * 1024)
        network_rows.append({
            'device': _pick_dict(iface, 'device', 'id', 'name', default='—'),
            'rx_bytes': int(rx) if rx is not None else None,
            'tx_bytes': int(tx) if tx is not None else None,
            'rx_display': _format_bytes(rx) if rx is not None else '—',
            'tx_display': _format_bytes(tx) if tx is not None else '—',
            'speed': iface.get('speed'),
        })

    space_rows: list[dict] = []
    for vol in data.get('space') or []:
        if not isinstance(vol, dict):
            continue
        total_b = _kb_to_bytes(vol.get('total')) or vol.get('total')
        used_b = _kb_to_bytes(vol.get('used')) or vol.get('used')
        try:
            total_b = int(total_b) if total_b is not None else None
            used_b = int(used_b) if used_b is not None else None
        except (TypeError, ValueError):
            total_b = None
            used_b = None
        pct = round(used_b / total_b * 100, 1) if total_b and used_b is not None else vol.get('used_percent')
        space_rows.append({
            'name': _pick_dict(vol, 'device', 'display_name', 'vol_path', default='—'),
            'used_percent': pct,
            'display': f'{_format_bytes(used_b)} / {_format_bytes(total_b)}' if total_b else '—',
        })

    disk_io = data.get('disk') if isinstance(data.get('disk'), dict) else {}
    disk_rows = []
    if isinstance(disk_io, dict):
        for dev, stats in disk_io.items():
            if not isinstance(stats, dict):
                continue
            disk_rows.append({
                'device': dev,
                'read': stats.get('read_byte') or stats.get('read'),
                'write': stats.get('write_byte') or stats.get('write'),
            })

    return {
        'cpu_percent': round(float(cpu_load), 1) if cpu_load is not None else None,
        'cpu': {
            'percent': round(float(cpu_load), 1) if cpu_load is not None else None,
            'user_load': cpu.get('user_load'),
            'system_load': cpu.get('system_load'),
            'other_load': cpu.get('other_load'),
            'loadavg': {
                '1m': cpu.get('1min_load') or cpu.get('load1'),
                '5m': cpu.get('5min_load') or cpu.get('load5'),
                '15m': cpu.get('15min_load') or cpu.get('load15'),
            },
        },
        'ram': ram,
        'swap': {
            'total_bytes': swap_total,
            'used_bytes': swap_used,
            'display': f'{_format_bytes(swap_used)} / {_format_bytes(swap_total)}',
        },
        'network': network_rows,
        'space': space_rows,
        'disk_io': disk_io,
        'disk_io_rows': disk_rows,
    }


def _read_dsm_system_info() -> dict:
    try:
        data = _dsm_request('SYNO.Core.System', 'info', version=3)
    except NasMonitorError:
        data = _dsm_request('SYNO.Core.System', 'info', version=1)
    uptime = data.get('uptime') or data.get('up_time') or data.get('system_time')
    return {
        'model': data.get('model') or data.get('model_string'),
        'version': data.get('version_string') or data.get('firmware_ver'),
        'hostname': data.get('hostname') or data.get('server_name'),
        'serial': data.get('serial'),
        'temperature': data.get('temperature'),
        'uptime_seconds': uptime,
        'uptime_display': _format_uptime(uptime),
        'time': _format_dsm_time(data.get('time_string') or data.get('time')),
    }


def _read_dsm_storage_disks() -> list[dict]:
    try:
        data = _dsm_request('SYNO.Storage.CGI.Storage', 'load_info', version=1, timeout=15)
    except NasMonitorError:
        return []
    rows: list[dict] = []
    for disk in data.get('disks') or []:
        if not isinstance(disk, dict):
            continue
        rows.append({
            'slot': _pick_dict(disk, 'slot_id', 'id', 'num_id', 'name', default='—'),
            'model': _pick_dict(disk, 'model', 'vendor', default='—'),
            'status': _pick_dict(disk, 'status', 'health_status', 'health', default='—'),
            'temperature': disk.get('temperature') or disk.get('temp'),
            'size_bytes': disk.get('size') or disk.get('capacity'),
        })
    return rows


def _read_dsm_widget_system_health() -> dict:
    data = _dsm_try_requests([
        ('SYNO.Core.System.SystemHealth', 'get', 1, None),
        ('SYNO.Core.System.Status', 'get', 1, None),
        ('SYNO.Core.System.Status', 'get', 2, None),
    ])
    status = data.get('status') or data.get('system_status') or data.get('health')
    if isinstance(status, dict):
        status = status.get('status') or status.get('value') or status.get('text')
    summary = data.get('summary') or data.get('message') or data.get('overview') or ''
    if isinstance(summary, dict):
        summary = summary.get('text') or summary.get('message') or ''

    items_out: list[dict] = []
    for item in data.get('items') or []:
        if not isinstance(item, dict):
            continue
        items_out.append({
            'id': _pick_dict(item, 'id', 'type', default=''),
            'title': _pick_dict(item, 'title', 'name', 'id', default='—'),
            'status': _pick_dict(item, 'status', 'status_key', 'health', default='—'),
            'detail': str(_pick_dict(item, 'desc', 'message', 'detail', default=''))[:160],
        })

    disks = _read_dsm_storage_disks()
    temps = [d['temperature'] for d in disks if d.get('temperature') not in (None, '', 0)]
    avg_temp = round(sum(float(t) for t in temps) / len(temps), 1) if temps else None

    return {
        'status': str(status) if status not in (None, '') else '—',
        'temperature': data.get('temperature') or avg_temp,
        'summary': str(summary)[:300] if summary else '',
        'items': items_out,
        'disks': disks[:12],
    }


def _parse_connected_user(item: dict) -> dict:
    return {
        'user': _pick_dict(item, 'who', 'user', 'username', 'name', default='—'),
        'ip': _pick_dict(item, 'from', 'ip', 'address', 'remote_ip', default='—'),
        'protocol': _pick_dict(item, 'description', 'protocol', 'type', 'service', default='—'),
        'time': _format_dsm_time(_pick_dict(item, 'connected_time', 'login_time', 'time', 'idle_time')),
        'agent': _pick_dict(item, 'agent', 'client', 'user_agent', default=''),
    }


def _read_dsm_widget_connected_users() -> list[dict]:
    items = _dsm_collect_items([
        ('SYNO.Core.CurrentConnection', 'list', 1, None),
        ('SYNO.Core.CurrentConnection', 'list', 2, None),
        ('SYNO.Core.System.Status', 'get', 1, {'type': 'connection'}),
    ], 'items', 'connections', 'users', 'connection')
    rows = [_parse_connected_user(item) for item in items[:30]]
    return rows


def _read_dsm_widget_scheduled_tasks() -> list[dict]:
    data = _dsm_try_requests([
        ('SYNO.Core.TaskScheduler', 'list', 3, None),
        ('SYNO.Core.TaskScheduler', 'list', 2, None),
        ('SYNO.Core.TaskScheduler', 'list', 1, None),
        ('SYNO.Core.EventScheduler', 'list', 1, None),
    ])
    rows: list[dict] = []
    for task in (data.get('tasks') or data.get('events') or [])[:40]:
        if not isinstance(task, dict):
            continue
        enabled = task.get('enable') if 'enable' in task else task.get('enabled')
        rows.append({
            'name': _pick_dict(task, 'name', 'task_name', default='—'),
            'type': _pick_dict(task, 'type', 'real_owner', 'owner', 'app', default='—'),
            'enabled': enabled,
            'next': _format_dsm_time(_pick_dict(task, 'next_trigger_time', 'next_run', 'next_time')),
            'last': _format_dsm_time(_pick_dict(task, 'last_run_time', 'last_trigger_time')),
            'last_result': _pick_dict(task, 'last_run_result', 'last_result', 'state', default='—'),
            'running': task.get('is_running'),
        })
    return rows


def _parse_log_row(log: dict) -> dict:
    return {
        'time': _format_dsm_time(_pick_dict(log, 'time', 'datetime', 'date', 'logtime')),
        'level': _pick_dict(log, 'level', 'severity', 'pri', default='—'),
        'source': _pick_dict(log, 'logtype', 'source', 'facility', 'who', 'program', default='—'),
        'user': _pick_dict(log, 'user', 'who', default=''),
        'message': str(_pick_dict(log, 'msg', 'message', 'desc', 'description', default='—'))[:280],
    }


def _read_dsm_widget_recent_logs(*, limit: int = 20) -> list[dict]:
    items = _dsm_collect_items([
        ('SYNO.Core.SyslogClient.Status', 'latestlog_get', 1, {'limit': str(limit)}),
        ('SYNO.Core.SyslogClient.Status', 'latestlog_get', 2, {'limit': str(limit)}),
        ('SYNO.Core.SyslogClient.Log', 'list', 1, {'limit': str(limit), 'offset': '0'}),
        ('SYNO.LogCenter.History', 'list', 1, {'limit': str(limit), 'offset': '0'}),
        ('SYNO.LogCenter.Client', 'list', 1, {'limit': str(limit), 'offset': '0'}),
    ], 'logs', 'items', 'log', 'history')
    return [_parse_log_row(log) for log in items[:limit]]


def _parse_backup_task(task: dict) -> dict:
    return {
        'name': _pick_dict(task, 'name', 'task_name', 'title', default='—'),
        'type': _pick_dict(task, 'type', 'task_type', 'plugin', 'backup_type', default=''),
        'status': _pick_dict(task, 'status', 'state', 'result', default='—'),
        'last': _format_dsm_time(_pick_dict(task, 'last_run_time', 'last_bkp_time', 'last_backup_time')),
        'next': _format_dsm_time(_pick_dict(task, 'next_run_time', 'next_bkp_time')),
        'destination': _pick_dict(task, 'dest', 'destination', 'target', default=''),
    }


def _read_dsm_widget_backup_tasks() -> list[dict]:
    items = _dsm_collect_items([
        ('SYNO.Backup.Task', 'list', 2, None),
        ('SYNO.Backup.Task', 'list', 1, None),
        ('SYNO.HyperBackup.Util', 'list_task', 2, None),
        ('SYNO.HyperBackup.Util', 'list_task', 1, None),
        ('SYNO.ActiveBackup.Task', 'list', 1, None),
    ], 'tasks', 'data', 'task_list')
    return [_parse_backup_task(task) for task in items[:25]]


def _parse_file_change(item: dict) -> dict:
    return {
        'time': _format_dsm_time(_pick_dict(item, 'time', 'mtime', 'datetime', 'logtime')),
        'user': _pick_dict(item, 'user', 'username', 'who', default='—'),
        'path': str(_pick_dict(item, 'path', 'file', 'filepath', 'name', default='—'))[:160],
        'action': _pick_dict(item, 'action', 'type', 'event', 'operation', default='—'),
        'ip': _pick_dict(item, 'ip', 'from', default=''),
    }


def _read_dsm_widget_file_changes(*, limit: int = 20) -> list[dict]:
    items = _dsm_collect_items([
        ('SYNO.Finder.FileSharing', 'get_changelog', 1, {'limit': str(limit)}),
        ('SYNO.Core.AuditLog', 'list', 1, {'limit': str(limit), 'offset': '0'}),
        ('SYNO.LogCenter.History', 'list', 1, {'limit': str(limit), 'logtype': 'file'}),
        ('SYNO.SynologyDrive.Log', 'list', 1, {'limit': str(limit)}),
    ], 'items', 'logs', 'changelog', 'history')
    return [_parse_file_change(item) for item in items[:limit]]


def _resource_from_utilization(util: dict | None) -> dict:
    util = util or {}
    ram = util.get('ram') or {}
    swap = util.get('swap') or {}
    cpu = util.get('cpu') or {}
    return {
        'cpu_percent': util.get('cpu_percent'),
        'cpu': cpu,
        'ram': ram,
        'swap': swap,
        'network': util.get('network') or [],
        'space': util.get('space') or [],
        'disk_io_rows': util.get('disk_io_rows') or [],
    }


def _empty_dsm_widgets() -> dict:
    return {
        'system_info': {},
        'system_health': {'status': '—', 'summary': '', 'items': [], 'disks': []},
        'resource': {
            'cpu_percent': None,
            'cpu': {'loadavg': {}},
            'ram': {},
            'swap': {},
            'network': [],
            'space': [],
            'disk_io_rows': [],
        },
        'storage': {'volumes': [], 'shares': []},
        'connected_users': [],
        'scheduled_tasks': [],
        'recent_logs': [],
        'backup_tasks': [],
        'file_changes': [],
        'portal_backup': {},
    }


def collect_dsm_widgets(
    *,
    volumes: list[dict] | None = None,
    shares: list[dict] | None = None,
    system_info: dict | None = None,
    utilization: dict | None = None,
    portal_backup: dict | None = None,
) -> dict:
    if not dsm_configured():
        return {}
    util = utilization or _read_dsm_utilization()
    info = system_info or _read_dsm_system_info()
    vols = volumes if volumes is not None else _read_dsm_volumes()
    share_rows = shares if shares is not None else []
    return {
        'system_info': info,
        'system_health': _read_dsm_widget_system_health(),
        'resource': _resource_from_utilization(util),
        'storage': {
            'volumes': vols,
            'shares': share_rows[:12],
        },
        'connected_users': _read_dsm_widget_connected_users(),
        'scheduled_tasks': _read_dsm_widget_scheduled_tasks(),
        'recent_logs': _read_dsm_widget_recent_logs(),
        'backup_tasks': _read_dsm_widget_backup_tasks(),
        'file_changes': _read_dsm_widget_file_changes(),
        'portal_backup': portal_backup or {},
    }


def _parse_process_memory_percent(proc: dict, ram_total_b: int | None) -> tuple[int | None, float | None]:
    """DSM Process API: mem thường là KB, không phải %."""
    mem_pct_raw = proc.get('memory_percent')
    if mem_pct_raw is not None:
        try:
            pct = float(mem_pct_raw)
            if 0 <= pct <= 100:
                return None, round(pct, 1)
        except (TypeError, ValueError):
            pass

    mem_raw = proc.get('memory') or proc.get('memory_usage') or proc.get('rss') or proc.get('mem')
    mem_bytes = None
    if mem_raw is not None:
        try:
            n = float(mem_raw)
            if n <= 0:
                mem_bytes = None
            elif n < 10_000_000:
                mem_bytes = int(n * 1024)
            else:
                mem_bytes = int(n)
        except (TypeError, ValueError):
            mem_bytes = None

    mem_pct = None
    if mem_bytes is not None and ram_total_b:
        mem_pct = round(mem_bytes / ram_total_b * 100, 1)
    return mem_bytes, mem_pct


def collect_nas_processes(*, limit: int = 25, ram_total_b: int | None = None) -> list[dict]:
    if not dsm_configured():
        return []
    try:
        data = _dsm_request('SYNO.Core.System.Process', 'list', version=1, timeout=15)
    except NasMonitorError:
        return []

    if ram_total_b is None:
        try:
            util = _read_dsm_utilization()
            ram_total_b = (util.get('ram') or {}).get('total_bytes')
        except NasMonitorError:
            ram_total_b = None

    rows: list[dict] = []
    for proc in data.get('process') or data.get('processes') or []:
        if isinstance(proc, dict):
            name = proc.get('name') or proc.get('command') or proc.get('process_name') or '—'
            try:
                pid = int(proc.get('pid') or 0)
            except (TypeError, ValueError):
                pid = 0
            mem_bytes, mem_pct = _parse_process_memory_percent(proc, ram_total_b)
            cpu_pct = proc.get('cpu') or proc.get('cpu_usage')
            rows.append({
                'pid': pid,
                'name': str(name)[:64],
                'cpu_percent': round(float(cpu_pct), 1) if cpu_pct is not None else None,
                'memory_percent': mem_pct,
                'memory_bytes': mem_bytes,
            })
    rows.sort(key=lambda row: row.get('memory_bytes') or 0, reverse=True)
    return rows[:limit]


def _rclone_about(remote: str, *, timeout: int = 45) -> dict | None:
    if not rclone_listing_available():
        return None
    proc = _run_rclone(['about', remote, '--json'], timeout=timeout)
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


def collect_nas_metrics(*, scope: str = 'full') -> dict:
    """Thu thập metrics NAS.

    scope:
      - performance: CPU/RAM/ổ đĩa + tiến trình (nhanh, không share/widgets/rclone about)
      - overview: thêm share, volume, backup
      - full: thêm widget DSM (tab Hệ thống DSM)
    """
    scope = (scope or 'full').strip().lower()
    if scope not in ('performance', 'overview', 'full'):
        scope = 'full'

    include_shares = scope in ('overview', 'full')
    include_widgets = scope == 'full'
    include_backup = scope in ('overview', 'full')
    include_rclone_disk = scope in ('overview', 'full')

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
        'widgets': _empty_dsm_widgets(),
        'error': None,
    }

    if dsm_ok:
        info = {}
        util = {}
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
            loadavg = (util.get('cpu') or {}).get('loadavg') or {}
            if loadavg:
                metrics['cpu']['loadavg'] = loadavg
        except NasMonitorError as exc:
            if not metrics['error']:
                metrics['error'] = str(exc)

        try:
            metrics['volumes'] = _read_dsm_volumes()
        except NasMonitorError:
            metrics['volumes'] = []

        try:
            metrics['processes'] = collect_nas_processes(
                ram_total_b=(metrics.get('ram') or {}).get('total_bytes'),
            )
        except NasMonitorError:
            metrics['processes'] = []

    if include_shares:
        try:
            metrics['shares'] = _collect_shares(volumes=metrics.get('volumes'))
        except Exception:
            metrics['shares'] = []

    if rclone_ok and include_rclone_disk:
        root_remote = default_nas_rclone_remote()
        root_about = _rclone_about(root_remote)
        if root_about:
            metrics['disk'] = {
                'path': root_remote,
                **root_about,
            }

    if rclone_ok and include_backup:
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

    if dsm_ok and include_widgets:
        try:
            metrics['widgets'] = collect_dsm_widgets(
                volumes=metrics.get('volumes'),
                shares=metrics.get('shares'),
                system_info=info if info else None,
                utilization=util if util else None,
                portal_backup=metrics.get('backup'),
            )
        except NasMonitorError:
            metrics['widgets'] = _empty_dsm_widgets()

    metrics['scope'] = scope
    return metrics
