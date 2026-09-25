"""Chặn kết nối VPS theo quốc gia. Trạng thái đọc file trên host; bật/tắt chạy script ufw."""

from __future__ import annotations

import os
import re
from pathlib import Path

from django.conf import settings

from audit.login_security import get_wan_whitelist
from audit.services.remote_access import fortigate_wan_ip
from audit.services.vps_monitor import VpsMonitorError, docker_available, docker_run_host_script

# Trước mắt chỉ Việt Nam. Thêm mã ISO vào đây khi cần mở thêm quốc gia.
COUNTRIES = {
    'VN': 'Việt Nam',
}
_CODE_RE = re.compile(r'^[A-Z]{2}$')


def _host_root() -> Path:
    return Path(getattr(settings, 'VPS_HOST_ROOT', '/host/root'))


def _script_path() -> str:
    root = (getattr(settings, 'HOST_PROJECT_DIR', None) or os.getenv('HOST_PROJECT_DIR') or '/opt/portaljustplay').rstrip('/')
    return f'{root}/scripts/vps-geo-access.sh'


def normalize_countries(codes) -> list[str]:
    """Chỉ giữ mã đang hỗ trợ. Rỗng thì mặc định Việt Nam."""
    found: list[str] = []
    raw = codes if isinstance(codes, (list, tuple)) else str(codes or '').replace(',', ' ').split()
    for item in raw:
        code = str(item or '').strip().upper()
        if _CODE_RE.match(code) and code in COUNTRIES and code not in found:
            found.append(code)
    return found or ['VN']


def bypass_ips() -> list[str]:
    """IP luôn được vào, kể cả khi GeoIP gắn nhầm quốc gia (văn phòng, Fortigate)."""
    seen: list[str] = []
    for raw in [*get_wan_whitelist(), fortigate_wan_ip()]:
        ip = (raw or '').strip()
        if ip and ip not in seen:
            seen.append(ip)
    return seen


def _read_state() -> dict[str, str]:
    path = _host_root() / 'etc/portaljustplay/geo-access.state'
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return data
    for line in text.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def geo_access_status() -> dict:
    from audit.login_security import get_security_config

    config = get_security_config()
    wanted = normalize_countries(config.allowed_countries)
    state = _read_state()
    host_enabled = state.get('enabled') == '1'
    try:
        prefixes = int(state.get('prefixes') or 0)
    except ValueError:
        prefixes = 0
    host_ok = _host_root().is_dir() and (_host_root() / 'etc').is_dir()
    return {
        'enabled': bool(config.geo_enabled) and host_enabled,
        'saved_enabled': bool(config.geo_enabled),
        'host_enabled': host_enabled,
        'countries': wanted,
        'country_labels': [COUNTRIES[code] for code in wanted],
        'catalog': [{'code': code, 'label': label} for code, label in COUNTRIES.items()],
        'prefixes': prefixes,
        'wan_if': state.get('wan_if') or 'eth0',
        'applied_at': state.get('applied_at') or '',
        'ipset': state.get('ipset') == 'yes',
        'host_ok': host_ok,
        'docker_ok': docker_available(),
        'script': _script_path(),
        'bypass_ips': bypass_ips(),
        'mismatch': bool(config.geo_enabled) != host_enabled,
    }


def apply_geo_access(*, enabled: bool, countries: list[str], admin_user=None) -> dict:
    codes = normalize_countries(countries)
    if not docker_available():
        raise VpsMonitorError('Docker socket không khả dụng — chỉ áp dụng được trên VPS.')
    action = 'apply' if enabled else 'disable'
    args = [action, ','.join(codes)] if enabled else [action]
    result = docker_run_host_script(
        _script_path(),
        *args,
        timeout=180.0,
        env={
            'GEO_BYPASS_IPS': ','.join(bypass_ips()),
            'GEO_WAN_IF': 'eth0',
            'HOST_PROJECT_DIR': (
                getattr(settings, 'HOST_PROJECT_DIR', None) or os.getenv('HOST_PROJECT_DIR') or '/opt/portaljustplay'
            ),
        },
    )
    from audit.login_security import get_security_config

    config = get_security_config()
    config.geo_enabled = bool(enabled)
    config.allowed_countries = codes
    if getattr(admin_user, 'is_authenticated', False):
        config.updated_by = admin_user
    config.save(update_fields=['geo_enabled', 'allowed_countries', 'updated_by', 'updated_at'])
    return {
        'enabled': bool(enabled),
        'countries': codes,
        'output': result.get('output') or '',
    }
