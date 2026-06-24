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

    if b'\r\n\r\n' not in raw:
        raise VpsMonitorError('Phản hồi Docker không hợp lệ.')
    header, body = raw.split(b'\r\n\r\n', 1)
    status = header.split(b'\r\n', 1)[0]
    if b' 204 ' in status:
        return {}
    if not any(code in status for code in (b' 200 ', b' 201 ')):
        detail = body.decode('utf-8', errors='replace')[:400]
        raise VpsMonitorError(detail or status.decode('utf-8', errors='replace'))
    if not body.strip():
        return {}
    return json.loads(body.decode('utf-8'))


def _container_memory_stats() -> list[dict]:
    containers = _docker_request('GET', '/containers/json')
    rows: list[dict] = []
    for item in containers:
        cid = item.get('Id', '')
        if not cid:
            continue
        names = [n.lstrip('/') for n in item.get('Names') or []]
        name = names[0] if names else cid[:12]
        try:
            stats = _docker_request('GET', f'/containers/{cid}/stats?stream=0&one-shot=1', timeout=15.0)
        except VpsMonitorError:
            continue
        mem = stats.get('memory_stats') or {}
        usage = int(mem.get('usage') or 0)
        limit = int(mem.get('limit') or 0)
        pct = round(usage / limit * 100, 1) if limit else None
        rows.append({
            'name': name,
            'memory_bytes': usage,
            'memory_limit_bytes': limit,
            'memory_percent': pct,
            'memory_display': f'{_format_bytes(usage)} / {_format_bytes(limit)}',
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
    containerd_bytes = _du_bytes(_host_root() / 'var/lib/containerd')
    docker_lib_bytes = _du_bytes(_host_root() / 'var/lib/docker')
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


def collect_vps_metrics() -> dict:
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
        'tips': [],
    }

    if not host_ok:
        metrics['tips'].append(
            'Chưa mount /proc và / của host vào container web — chỉ hiển thị số liệu trong container.',
        )

    if docker_ok:
        try:
            metrics['docker']['containers'] = _container_memory_stats()
            metrics['docker']['summary'] = _docker_disk_summary()
        except VpsMonitorError as exc:
            metrics['docker']['error'] = str(exc)
    else:
        metrics['tips'].append('Chưa mount Docker socket — không xem được container và không chạy tối ưu Docker.')

    summary = metrics['docker'].get('summary') or {}
    if summary.get('containerd_bytes', 0) and summary['containerd_bytes'] > 5 * 1024 ** 3:
        metrics['tips'].append('Docker build cache / containerd > 5 GB — nên dọn build cache.')

    if summary.get('orphan_volumes'):
        names = ', '.join(v['name'] for v in summary['orphan_volumes'][:3])
        metrics['tips'].append(f'Có volume Docker không dùng: {names}')

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
        'description': 'Gỡ image không gắn container (migrate cũ, tag cũ…).',
        'confirm': 'Xóa mọi image Docker không được container sử dụng?',
        'danger': False,
    },
    'remove_rembg_volume': {
        'label': 'Xóa volume rembg_models',
        'description': 'Model AI xóa nền cũ (~170 MB) — không còn dùng sau khi gỡ công cụ.',
        'confirm': 'Xóa volume portaljustplay_rembg_models?',
        'danger': False,
    },
    'remove_migrate_image': {
        'label': 'Xóa image migrate cũ',
        'description': 'Image portaljustplay-migrate (~2.7 GB) chỉ dùng một lần khi migrate.',
        'confirm': 'Xóa image portaljustplay-migrate:latest?',
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

    if action_id == 'remove_rembg_volume':
        _docker_request('DELETE', '/volumes/portaljustplay_rembg_models?force=0')
        return {'message': 'Đã xóa volume portaljustplay_rembg_models.'}

    if action_id == 'remove_migrate_image':
        _docker_request('DELETE', '/images/portaljustplay-migrate:latest?force=1')
        return {'message': 'Đã xóa image portaljustplay-migrate:latest.'}

    raise VpsMonitorError('Thao tác không hợp lệ.')
