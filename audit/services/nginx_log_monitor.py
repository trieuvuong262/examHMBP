"""Tóm tắt access log nginx (container) để theo dõi bot / lỗi trên trang bảo mật."""

from __future__ import annotations

import re
import time
from collections import Counter
from urllib.parse import unquote

from audit.services.vps_monitor import VpsMonitorError, docker_available, docker_container_logs

WATCH_HOURS = (6, 24, 48)
DEFAULT_HOURS = 24
MAX_RECENT = 80
MAX_TOP = 15

# Đường / UA điển hình của scanner — không phải traffic nhân viên.
_SCANNER_PATHS = (
    '/.env',
    '/.git',
    '/wp-admin',
    '/wp-login',
    '/xmlrpc.php',
    '/phpmyadmin',
    '/administrator',
    '/vendor/phpunit',
    '/actuator',
    '/.aws',
    '/cgi-bin',
    '/boaform',
    '/manager/html',
    '/solr/',
    '/jenkins',
    '/telescope',
    '/debug/default',
    '/shell',
    '/eval-stdin',
    '/autodiscover',
    '/owa/',
    '/webfig',
    '/HNAP1',
    '/sdk',
)
_SCANNER_UA = (
    'sqlmap',
    'nikto',
    'masscan',
    'zgrab',
    'dirbuster',
    'gobuster',
    'nuclei',
    'httpx',
    'nessus',
    'openvas',
    'wpscan',
)
_NOISE_PATHS = {
    '/favicon.ico',
    '/apple-touch-icon.png',
    '/apple-touch-icon-precomposed.png',
}
_TS_PREFIX_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\s+',
)
_ACCESS_RE = re.compile(
    r'(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>[^"\s]+)(?:\s+[^"]*)?"\s+'
    r'(?P<status>\d{3})\s+(?P<size>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?',
)


def clamp_hours(raw) -> int:
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    return hours if hours in WATCH_HOURS else DEFAULT_HOURS


def _path_only(raw: str) -> str:
    path = unquote((raw or '').split('?', 1)[0] or '/')
    if len(path) > 180:
        return path[:177] + '...'
    return path


def _is_scanner_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in _SCANNER_PATHS)


def _is_scanner_ua(ua: str) -> bool:
    lowered = (ua or '').lower()
    return any(marker in lowered for marker in _SCANNER_UA)


def parse_access_line(line: str) -> dict | None:
    text = (line or '').strip()
    if not text:
        return None
    text = _TS_PREFIX_RE.sub('', text, count=1)
    match = _ACCESS_RE.search(text)
    if not match:
        return None
    path = _path_only(match.group('path'))
    try:
        status = int(match.group('status'))
    except ValueError:
        return None
    ua = (match.group('ua') or '')[:180]
    scanner = _is_scanner_path(path) or _is_scanner_ua(ua)
    method = match.group('method')
    return {
        'ip': match.group('ip'),
        'time': match.group('time'),
        'method': method,
        'path': path,
        'status': status,
        'ua': ua,
        'scanner': scanner,
        'login_post': method == 'POST' and path.startswith('/accounts/login'),
        'noise': path.lower() in _NOISE_PATHS and status in (404, 400),
    }


def summarize_access_lines(text: str, *, hours: int = DEFAULT_HOURS) -> dict:
    parsed: list[dict] = []
    skipped = 0
    for raw in (text or '').splitlines():
        row = parse_access_line(raw)
        if row is None:
            if raw.strip():
                skipped += 1
            continue
        parsed.append(row)

    interesting = [row for row in parsed if not row['noise']]
    status_4xx = sum(1 for row in interesting if 400 <= row['status'] < 500)
    status_5xx = sum(1 for row in interesting if row['status'] >= 500)
    scanners = [row for row in interesting if row['scanner']]
    login_posts = [row for row in interesting if row['login_post']]
    errors = [
        row for row in interesting
        if row['status'] >= 400 or row['scanner'] or row['login_post']
    ]

    path_counter: Counter[str] = Counter()
    ip_counter: Counter[str] = Counter()
    for row in errors:
        path_counter[f"{row['status']} {row['method']} {row['path']}"] += 1
        ip_counter[row['ip']] += 1

    recent = list(reversed(errors[-MAX_RECENT:]))
    return {
        'hours': hours,
        'line_count': len(parsed),
        'skipped_lines': skipped,
        'count_4xx': status_4xx,
        'count_5xx': status_5xx,
        'count_scanner': len(scanners),
        'count_login_post': len(login_posts),
        'top_paths': path_counter.most_common(MAX_TOP),
        'top_ips': ip_counter.most_common(MAX_TOP),
        'recent': recent,
    }


def empty_nginx_watch(*, hours: int = DEFAULT_HOURS, error: str | None = None) -> dict:
    return {
        'hours': hours,
        'available': False,
        'container': None,
        'error': error,
        'line_count': 0,
        'skipped_lines': 0,
        'count_4xx': 0,
        'count_5xx': 0,
        'count_scanner': 0,
        'count_login_post': 0,
        'top_paths': [],
        'top_ips': [],
        'recent': [],
    }


def collect_nginx_log_watch(*, hours: int = DEFAULT_HOURS) -> dict:
    hours = clamp_hours(hours)
    if not docker_available():
        return empty_nginx_watch(
            hours=hours,
            error='Không đọc được Docker socket — tab này chỉ có số liệu trên VPS.',
        )
    try:
        payload = docker_container_logs(
            'nginx',
            since=int(time.time()) - hours * 3600,
            tail=4000,
        )
    except VpsMonitorError as exc:
        return empty_nginx_watch(hours=hours, error=str(exc))

    summary = summarize_access_lines(payload.get('text') or '', hours=hours)
    summary['available'] = True
    summary['container'] = payload.get('name')
    summary['error'] = None
    return summary
