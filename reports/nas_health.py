"""Kiểm tra nhanh tình trạng thư mục lưu trữ NAS cho module Báo cáo.

Dùng để đánh dấu NAS lỗi khi ghi file thất bại và phục vụ fallback lưu tạm trên VPS.
Không hiển thị cảnh báo trên giao diện người dùng.

QUAN TRỌNG — vì sao KHÔNG kiểm tra bằng cách đọc mount ``/mnt/nas-portal``:
Khi NAS mất kết nối, mount rclone/FUSE bị treo, mọi thao tác I/O (``os.access``,
``listdir``, ``ls``...) rơi vào trạng thái **D (uninterruptible sleep)** — không thể
kill kể cả bằng ``subprocess timeout`` hay ``gunicorn --timeout``. Chỉ cần một request
chạm mount là worker gunicorn kẹt cứng, cạn worker → sập toàn site.
Vì vậy probe ở đây kiểm tra NAS **qua mạng bằng rclone CLI** (tiến trình network bình
thường, timeout kill được), tuyệt đối không chạm vào mount FUSE.
"""

from __future__ import annotations

import logging
import subprocess

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_KEY = 'reports:nas_storage_available'
_CACHE_TTL_OK = 60
_CACHE_TTL_DOWN = 20

# rclone timeout ngắn để probe nhanh; subprocess timeout là chốt chặn cứng.
_RCLONE_CONNECT_TIMEOUT = '4s'
_RCLONE_IO_TIMEOUT = '4s'
_SUBPROCESS_TIMEOUT_SEC = 8.0


def _rclone_probe_env() -> dict:
    import os

    env = os.environ.copy()
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and os.path.isfile(config):
        env['RCLONE_CONFIG'] = config
    return env


def _probe_remote_reachable() -> bool:
    """Kiểm tra NAS qua rclone CLI (network) — KHÔNG đụng mount FUSE.

    ``rclone lsd`` là tiến trình mạng thông thường: nếu NAS mất kết nối nó sẽ lỗi
    trong ``--contimeout`` hoặc bị ``subprocess timeout`` kill an toàn.
    """
    remote = (getattr(settings, 'NAS_RCLONE_REMOTE', 'synology:') or 'synology:').strip()
    cmd = [
        'rclone', 'lsd', remote,
        '--contimeout', _RCLONE_CONNECT_TIMEOUT,
        '--timeout', _RCLONE_IO_TIMEOUT,
        '--retries', '1',
        '--low-level-retries', '1',
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SEC,
            check=False,
            env=_rclone_probe_env(),
        )
    except subprocess.TimeoutExpired:
        logger.warning('Probe NAS: rclone lsd quá %.0fs — coi như NAS lỗi', _SUBPROCESS_TIMEOUT_SEC)
        return False
    except (OSError, ValueError):
        logger.exception('Probe NAS: không chạy được rclone')
        return False
    if proc.returncode != 0:
        logger.warning('Probe NAS lỗi rc=%s: %s', proc.returncode, (proc.stderr or '').strip()[:200])
        return False
    return True


def _probe() -> bool:
    try:
        return _probe_remote_reachable()
    except Exception:  # noqa: BLE001 - probe không được phép làm sập trang
        logger.exception('Probe NAS storage thất bại')
        return False


def report_storage_available(*, use_cache: bool = True) -> bool:
    """True nếu NAS đang sẵn sàng ghi đính kèm báo cáo (kết quả cache ngắn)."""
    if use_cache:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return cached
    available = _probe()
    cache.set(_CACHE_KEY, available, _CACHE_TTL_OK if available else _CACHE_TTL_DOWN)
    return available


def mark_storage_unavailable() -> None:
    """Đánh dấu NAS lỗi ngay (gọi khi một lần ghi file thất bại)."""
    cache.set(_CACHE_KEY, False, _CACHE_TTL_DOWN)
