"""Giám sát tài nguyên VPS (RAM/CPU/SSD) và thao tác tối ưu Docker an toàn."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from django.conf import settings


class VpsMonitorError(Exception):
    pass


def _host_proc() -> Path:
    return Path(getattr(settings, 'VPS_HOST_PROC', '/host/proc'))


def _host_root() -> Path:
    return Path(getattr(settings, 'VPS_HOST_ROOT', '/host/root'))


def _docker_socket() -> Path:
    return Path(getattr(settings, 'VPS_DOCKER_SOCKET', '/var/run/docker.sock'))


def host_monitoring_available() -> bool:
    proc = _host_proc() / 'meminfo'
    root = _host_root()
    return proc.is_file() and root.is_dir()


def docker_available() -> bool:
    sock = _docker_socket()
    return sock.exists() and os.access(sock, os.R_OK | os.W_OK)


def _read_meminfo() -> dict[str, int]:
    candidates = [_host_proc() / 'meminfo', Path('/proc/meminfo')]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return {}
    data: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'^(\w+):\s+(\d+)', line)
        if match:
            data[match.group(1)] = int(match.group(2)) * 1024
    return data


def _read_loadavg() -> tuple[float, float, float]:
    candidates = [_host_proc() / 'loadavg', Path('/proc/loadavg')]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return 0.0, 0.0, 0.0
    parts = path.read_text(encoding='utf-8').split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def _read_cpu_usage_percent(sample_sec: float = 0.15) -> float | None:
    candidates = [_host_proc() / 'stat', Path('/proc/stat')]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return None

    def read_cpu():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.startswith('cpu '):
                parts = [int(x) for x in line.split()[1:]]
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                total = sum(parts)
                return idle, total
        return None

    first = read_cpu()
    if not first:
        return None
    time.sleep(sample_sec)
    second = read_cpu()
    if not second:
        return None
    idle_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    if total_delta <= 0:
        return 0.0
    return round(100.0 * (1.0 - idle_delta / total_delta), 1)


def _disk_usage(path: Path) -> dict | None:
    try:
        if hasattr(os, 'statvfs'):
            usage = os.statvfs(path)
            total = usage.f_frsize * usage.f_blocks
            free = usage.f_frsize * usage.f_bavail
        else:
            usage = shutil.disk_usage(path)
            total = usage.total
            free = usage.free
    except OSError:
        return None
    used = total - free
    pct = (used / total * 100.0) if total else 0.0
    return {
        'path': str(path),
        'total_bytes': total,
        'used_bytes': used,
        'free_bytes': free,
        'used_percent': round(pct, 1),
    }


def _du_bytes(path: Path, *, timeout: int = 20) -> int | None:
    if not path.exists():
        return None
    try:
        proc = subprocess.run(
            ['du', '-sb', str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or '').strip().split('\n', 1)[0]
    if not line:
        return None
    return int(line.split()[0])


def _format_bytes(value: int | float | None) -> str:
    if value is None:
        return '—'
    n = float(value)
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    for unit in units:
        if n < 1024 or unit == units[-1]:
            if unit == 'B':
                return f'{int(n)} {unit}'
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def _decode_chunked_body(data: bytes) -> bytes:
    out = bytearray()
    pos = 0
    while pos < len(data):
        line_end = data.find(b'\r\n', pos)
        if line_end < 0:
            break
        size_hex = data[pos:line_end].decode('ascii', errors='replace').split(';', 1)[0].strip()
        try:
            chunk_size = int(size_hex, 16)
        except ValueError:
            break
        pos = line_end + 2
        if chunk_size == 0:
            break
        out.extend(data[pos:pos + chunk_size])
        pos += chunk_size + 2
    return bytes(out)


def _docker_response_body(raw: bytes) -> bytes:
    if b'\r\n\r\n' not in raw:
        raise VpsMonitorError('Phản hồi Docker không hợp lệ.')
    header_bytes, body = raw.split(b'\r\n\r\n', 1)
    header_lines = header_bytes.decode('utf-8', errors='replace').split('\r\n')
    status = header_lines[0]
    headers = {}
    for line in header_lines[1:]:
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip().lower()] = value.strip()

    if b' 204 ' in status.encode():
        return b''
    if not any(code in status for code in (' 200 ', ' 201 ')):
        detail = body.decode('utf-8', errors='replace')[:400]
        raise VpsMonitorError(detail or status)

    encoding = headers.get('transfer-encoding', '').lower()
    if encoding == 'chunked':
        body = _decode_chunked_body(body)

    content_length = headers.get('content-length')
    if content_length and content_length.isdigit():
        body = body[:int(content_length)]

    return body


def _parse_docker_json(body: bytes) -> dict | list:
    text = body.decode('utf-8', errors='replace').strip()
    if not text:
        return {}
    decoder = json.JSONDecoder()
    try:
        obj, _idx = decoder.raw_decode(text)
        return obj
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj, _idx = decoder.raw_decode(line)
                return obj
            except json.JSONDecodeError:
                continue
        raise VpsMonitorError('Docker trả JSON không đọc được.')


def _cpu_percent_from_stats(stats: dict) -> float | None:
    cpu = stats.get('cpu_stats') or {}
    precpu = stats.get('precpu_stats') or {}
    try:
        cpu_usage = cpu.get('cpu_usage') or {}
        precpu_usage = precpu.get('cpu_usage') or {}
        cpu_delta = int(cpu_usage.get('total_usage') or 0) - int(precpu_usage.get('total_usage') or 0)
        system_delta = int(cpu.get('system_cpu_usage') or 0) - int(precpu.get('system_cpu_usage') or 0)
        if system_delta <= 0 or cpu_delta < 0:
            return None
        online = cpu.get('online_cpus') or len(cpu_usage.get('percpu_usage') or []) or 1
        return round((cpu_delta / system_delta) * int(online) * 100.0, 1)
    except (TypeError, ValueError):
        return None


def _network_bytes_from_stats(stats: dict) -> tuple[int, int]:
    rx = tx = 0
    for iface in (stats.get('networks') or {}).values():
        rx += int(iface.get('rx_bytes') or 0)
        tx += int(iface.get('tx_bytes') or 0)
    return rx, tx


def _docker_request(method: str, path: str, *, timeout: float = 120.0) -> dict | list:
    sock_path = _docker_socket()
    if not sock_path.exists():
        raise VpsMonitorError('Docker socket không khả dụng trên container web.')

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(sock_path))
        payload = (
            f'{method} {path} HTTP/1.1\r\n'
            'Host: localhost\r\n'
            'Connection: close\r\n'
            '\r\n'
        )
        sock.sendall(payload.encode('utf-8'))
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b''.join(chunks)
    finally:
        sock.close()

    body = _docker_response_body(raw)
    if not body.strip():
        return {}
    return _parse_docker_json(body)


def _container_stats() -> list[dict]:
    containers = _docker_request('GET', '/containers/json?all=0')
    rows: list[dict] = []
    for item in containers:
        cid = item.get('Id', '')
        if not cid:
            continue
        names = [n.lstrip('/') for n in item.get('Names') or []]
        name = names[0] if names else cid[:12]
        short_id = cid[:12]
        image = (item.get('Image') or '').split('@', 1)[0]
        state = (item.get('State') or '').capitalize() or '—'
        status = item.get('Status') or '—'
        try:
            stats = _docker_request('GET', f'/containers/{cid}/stats?stream=0&one-shot=1', timeout=15.0)
        except VpsMonitorError:
            stats = {}
        mem = stats.get('memory_stats') or {}
        usage = int(mem.get('usage') or 0)
        limit = int(mem.get('limit') or 0)
        cache = int((mem.get('stats') or {}).get('cache') or 0)
        pct = round(usage / limit * 100, 1) if limit else None
        cpu_pct = _cpu_percent_from_stats(stats)
        rx, tx = _network_bytes_from_stats(stats)
        pids = int((stats.get('pids_stats') or {}).get('current') or 0)
        rows.append({
            'id': short_id,
            'name': name,
            'image': image,
            'state': state,
            'status': status,
            'memory_bytes': usage,
            'memory_limit_bytes': limit,
            'memory_cache_bytes': cache,
            'memory_percent': pct,
            'memory_display': f'{_format_bytes(usage)} / {_format_bytes(limit)}',
            'cpu_percent': cpu_pct,
            'network_rx_bytes': rx,
            'network_tx_bytes': tx,
            'pids': pids,
        })
    rows.sort(key=lambda row: row['memory_bytes'], reverse=True)
    return rows


def _docker_disk_summary() -> dict:
    images = _docker_request('GET', '/images/json')
    volumes = (_docker_request('GET', '/volumes') or {}).get('Volumes') or []
    image_bytes = sum(int(img.get('Size') or 0) for img in images)
    volume_bytes = sum(int(vol.get('UsageData', {}).get('Size') or 0) for vol in volumes)
    reclaimable_images = 0
    for img in images:
        tags = img.get('RepoTags') or []
        if not tags or tags == ['<none>:<none>']:
            reclaimable_images += int(img.get('Size') or 0)
    containerd_bytes = _du_bytes(_host_root() / 'var/lib/containerd', timeout=8)
    docker_lib_bytes = _du_bytes(_host_root() / 'var/lib/docker', timeout=5)
    return {
        'images_bytes': image_bytes,
        'images_reclaimable_bytes': reclaimable_images,
        'volumes_bytes': volume_bytes,
        'volume_count': len(volumes),
        'containerd_bytes': containerd_bytes,
        'docker_lib_bytes': docker_lib_bytes,
        'orphan_volumes': [
            {
                'name': vol.get('Name'),
                'bytes': int(vol.get('UsageData', {}).get('Size') or 0),
            }
            for vol in volumes
            if int(vol.get('UsageData', {}).get('RefCount') or 0) == 0
        ],
    }


def _collect_host_processes_from_proc(*, limit: int = 25) -> list[dict]:
    proc_root = _host_proc()
    if not proc_root.is_dir():
        return []
    rows: list[dict] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        status_path = entry / 'status'
        if not status_path.is_file():
            continue
        name = ''
        rss_kb = 0
        try:
            for line in status_path.read_text(encoding='utf-8', errors='replace').splitlines()[:40]:
                if line.startswith('Name:'):
                    name = line.split(':', 1)[1].strip()
                elif line.startswith('VmRSS:'):
                    rss_kb = int(line.split()[1])
        except OSError:
            continue
        if not name or rss_kb <= 0:
            continue
        rows.append({
            'pid': int(entry.name),
            'name': name[:64],
            'cpu_percent': None,
            'memory_percent': None,
            'memory_bytes': rss_kb * 1024,
        })
    rows.sort(key=lambda row: row['memory_bytes'], reverse=True)
    return rows[:limit]


def collect_host_processes(*, limit: int = 25) -> list[dict]:
    """Top tiến trình trên VPS host — giống tab Processes của Task Manager."""
    if not host_monitoring_available():
        return []

    host_root = _host_root()
    chroot_bin = shutil.which('chroot')
    if chroot_bin and host_root.is_dir():
        try:
            proc = subprocess.run(
                [
                    chroot_bin,
                    str(host_root),
                    'ps',
                    '-eo', 'pid,comm,%cpu,%mem,rss',
                    '--no-headers',
                    '--sort=-%mem',
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                rows: list[dict] = []
                for line in proc.stdout.strip().splitlines()[:limit]:
                    parts = line.split(None, 4)
                    if len(parts) < 5:
                        continue
                    try:
                        rows.append({
                            'pid': int(parts[0]),
                            'name': parts[1][:64],
                            'cpu_percent': round(float(parts[2]), 1),
                            'memory_percent': round(float(parts[3]), 1),
                            'memory_bytes': int(parts[4]) * 1024,
                        })
                    except ValueError:
                        continue
                if rows:
                    return rows
        except (OSError, subprocess.TimeoutExpired):
            pass

    return _collect_host_processes_from_proc(limit=limit)


def empty_vps_metrics() -> dict:
    """Khung metrics nhẹ cho render trang — dữ liệu thật tải qua API."""
    host_ok = host_monitoring_available()
    return {
        'scope': 'shell',
        'hostname': None,
        'host_monitoring': host_ok,
        'docker_available': docker_available(),
        'collected_at': None,
        'ram': {},
        'cpu': {'percent': None, 'cores': os.cpu_count() or 1, 'loadavg': {}},
        'disk': None,
        'docker': {'containers': [], 'summary': {}},
        'processes': [],
        'error': None,
    }


def collect_vps_metrics(*, scope: str = 'full') -> dict:
    """scope: performance (CPU/RAM/ổ đĩa) | full (+ Docker, tiến trình)."""
    scope = (scope or 'full').strip().lower()
    if scope not in ('performance', 'full'):
        scope = 'full'
    include_docker = scope == 'full'
    include_processes = scope == 'full'

    host_ok = host_monitoring_available()
    docker_ok = docker_available()
    scope = 'host' if host_ok else 'container'

    mem = _read_meminfo()
    ram_total = mem.get('MemTotal')
    ram_available = mem.get('MemAvailable') or mem.get('MemFree')
    ram_used = (ram_total - ram_available) if (ram_total and ram_available is not None) else None
    ram_pct = round(ram_used / ram_total * 100, 1) if ram_total and ram_used is not None else None

    disk_root = _disk_usage(_host_root() if host_ok else Path('/'))
    load1, load5, load15 = _read_loadavg()
    cpu_pct = _read_cpu_usage_percent()

    hostname_path = _host_root() / 'etc/hostname' if host_ok else Path('/etc/hostname')
    hostname = (
        hostname_path.read_text(encoding='utf-8', errors='replace').strip()
        if hostname_path.is_file()
        else platform.node() or 'vps'
    )

    metrics: dict = {
        'scope': scope,
        'hostname': hostname,
        'host_monitoring': host_ok,
        'docker_available': docker_ok,
        'collected_at': time.time(),
        'ram': {
            'total_bytes': ram_total,
            'used_bytes': ram_used,
            'available_bytes': ram_available,
            'used_percent': ram_pct,
            'display': f'{_format_bytes(ram_used)} / {_format_bytes(ram_total)}',
        },
        'cpu': {
            'percent': cpu_pct,
            'cores': os.cpu_count() or 1,
            'loadavg': {'1m': load1, '5m': load5, '15m': load15},
        },
        'disk': disk_root,
        'docker': {
            'containers': [],
            'summary': {},
        },
        'processes': [],
    }

    if include_docker and docker_ok:
        try:
            metrics['docker']['containers'] = _container_stats()
        except VpsMonitorError as exc:
            metrics['docker']['error'] = str(exc)
        try:
            metrics['docker']['summary'] = _docker_disk_summary()
        except VpsMonitorError as exc:
            metrics['docker']['summary_error'] = str(exc)

    if include_processes and host_ok:
        try:
            metrics['processes'] = collect_host_processes()
        except OSError:
            metrics['processes'] = []

    metrics['scope'] = scope
    return metrics


OPTIMIZE_ACTIONS: dict[str, dict] = {
    'prune_build_cache': {
        'label': 'Dọn Docker build cache',
        'description': 'Giải phóng cache build (thường hàng chục GB sau nhiều lần deploy).',
        'confirm': 'Dọn toàn bộ Docker build cache? Container đang chạy không bị dừng.',
        'danger': False,
    },
    'prune_images': {
        'label': 'Xóa image Docker không dùng',
        'description': 'Gỡ image không gắn container (tag cũ, image lẻ…).',
        'confirm': 'Xóa mọi image Docker không được container sử dụng?',
        'danger': False,
    },
}


def list_optimize_actions() -> list[dict]:
    return [
        {'id': key, **meta}
        for key, meta in OPTIMIZE_ACTIONS.items()
    ]


def run_optimize_action(action_id: str) -> dict:
    if action_id not in OPTIMIZE_ACTIONS:
        raise VpsMonitorError('Thao tác không hợp lệ.')
    if not docker_available():
        raise VpsMonitorError('Docker socket không khả dụng.')

    if action_id == 'prune_build_cache':
        result = _docker_request('POST', '/build/prune?all=1')
        reclaimed = int(result.get('SpaceReclaimed') or 0)
        return {
            'message': f'Đã dọn build cache — giải phóng {_format_bytes(reclaimed)}.',
            'reclaimed_bytes': reclaimed,
        }

    if action_id == 'prune_images':
        result = _docker_request('POST', '/images/prune?all=1')
        reclaimed = int(result.get('SpaceReclaimed') or 0)
        deleted = result.get('ImagesDeleted') or []
        return {
            'message': f'Đã xóa {len(deleted)} image — giải phóng {_format_bytes(reclaimed)}.',
            'reclaimed_bytes': reclaimed,
            'deleted_count': len(deleted),
        }

    raise VpsMonitorError('Thao tác không hợp lệ.')
