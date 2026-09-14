"""Bảo vệ worker khỏi mount FUSE treo (D-state) khi NAS mất kết nối.

VẤN ĐỀ
------
NAS được mount vào ``/mnt/nas-portal`` bằng rclone/FUSE. Khi NAS mất kết nối,
mọi thao tác I/O trên mount (``os.access``, ``Path.is_dir``, ``open``,
``listdir``...) rơi vào trạng thái **D — uninterruptible sleep**. Tiến trình ở
D-state KHÔNG thể bị kill: ``subprocess timeout``, ``gunicorn --timeout``,
``SIGKILL`` đều vô hiệu. Chỉ cần vài request chạm mount là cạn 10 gunicorn
worker → sập toàn site.

GIẢI PHÁP
---------
Trước khi chạm mount, hỏi ``mount_io_safe()``:

* Đường dẫn KHÔNG nằm trên mount FUSE (dev/test dùng thư mục thường) → cho phép
  ngay, hành vi giữ nguyên như trước.
* Đường dẫn nằm trên mount FUSE → chỉ cho phép khi NAS còn liên lạc được, xác
  định bằng ``rclone lsd`` qua mạng (tiến trình network bình thường, timeout
  kill được), kết quả cache ngắn.

Việc phát hiện mount FUSE đọc ``/proc/self/mountinfo`` — procfs không bao giờ
block, kể cả khi mount bên dưới đã treo.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

MOUNTINFO_PATH = '/proc/self/mountinfo'

# Cache kết quả probe NAS qua mạng (dùng chung toàn portal).
_REMOTE_CACHE_KEY = 'nas:remote_reachable'
_REMOTE_TTL_OK = 60
_REMOTE_TTL_DOWN = 20

# rclone timeout ngắn để probe nhanh; subprocess timeout là chốt chặn cứng.
_RCLONE_CONNECT_TIMEOUT = '4s'
_RCLONE_IO_TIMEOUT = '4s'
_SUBPROCESS_TIMEOUT_SEC = 8.0

# Cache danh sách mount FUSE trong process (procfs rẻ nhưng bị gọi rất nhiều).
_FUSE_CACHE_TTL_SEC = 5.0
_fuse_cache: tuple[float, tuple[str, ...]] | None = None


def _unescape_mountinfo(value: str) -> str:
    """mountinfo escape khoảng trắng/tab thành \\040, \\011..."""
    if '\\' not in value:
        return value
    out = []
    i = 0
    while i < len(value):
        if value[i] == '\\' and i + 3 < len(value) and value[i + 1:i + 4].isdigit():
            try:
                out.append(chr(int(value[i + 1:i + 4], 8)))
                i += 4
                continue
            except ValueError:
                pass
        out.append(value[i])
        i += 1
    return ''.join(out)


def _read_fuse_mount_points() -> tuple[str, ...]:
    """Các mount point kiểu fuse* theo /proc/self/mountinfo. Không chạm mount."""
    try:
        with open(MOUNTINFO_PATH, 'r', encoding='utf-8', errors='replace') as handle:
            raw = handle.read()
    except OSError:
        # Không phải Linux (dev Windows) hoặc không đọc được procfs.
        return ()

    points: list[str] = []
    for line in raw.splitlines():
        # <id> <parent> <maj:min> <root> <mountpoint> <opts> [optional...] - <fstype> <source> <sopts>
        head, _, tail = line.partition(' - ')
        if not tail:
            continue
        head_fields = head.split(' ')
        tail_fields = tail.split(' ')
        if len(head_fields) < 5 or not tail_fields:
            continue
        fstype = tail_fields[0]
        if not fstype.startswith('fuse'):
            continue
        points.append(_unescape_mountinfo(head_fields[4]))
    return tuple(points)


def fuse_mount_points(*, use_cache: bool = True) -> tuple[str, ...]:
    global _fuse_cache

    now = time.monotonic()
    if use_cache and _fuse_cache is not None:
        cached_at, points = _fuse_cache
        if now - cached_at < _FUSE_CACHE_TTL_SEC:
            return points
    points = _read_fuse_mount_points()
    _fuse_cache = (now, points)
    return points


def reset_fuse_cache() -> None:
    """Xoá cache mountinfo trong process (dùng cho test)."""
    global _fuse_cache
    _fuse_cache = None


def path_on_fuse_mount(path) -> bool:
    """True nếu ``path`` nằm trên (hoặc chính là) một mount FUSE.

    Chỉ so sánh chuỗi đường dẫn — không stat, không chạm filesystem.
    """
    points = fuse_mount_points()
    if not points:
        return False
    try:
        target = os.path.normpath(str(path))
    except (TypeError, ValueError):
        return False
    for point in points:
        normalized = os.path.normpath(point)
        if target == normalized:
            return True
        prefix = normalized if normalized.endswith(os.sep) else normalized + os.sep
        if target.startswith(prefix):
            return True
    return False


def _rclone_probe_env() -> dict:
    env = os.environ.copy()
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and os.path.isfile(config):
        env['RCLONE_CONFIG'] = config
    return env


def _probe_remote_reachable() -> bool:
    """Kiểm tra NAS qua rclone CLI (network) — KHÔNG đụng mount FUSE."""
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


def remote_reachable(*, use_cache: bool = True) -> bool:
    """True nếu NAS còn liên lạc được qua mạng (cache ngắn, không chạm mount)."""
    if use_cache:
        cached = cache.get(_REMOTE_CACHE_KEY)
        if cached is not None:
            return cached
    try:
        available = _probe_remote_reachable()
    except Exception:  # noqa: BLE001 - probe không được phép làm sập trang
        logger.exception('Probe NAS thất bại')
        available = False
    cache.set(_REMOTE_CACHE_KEY, available, _REMOTE_TTL_OK if available else _REMOTE_TTL_DOWN)
    return available


def mark_remote_unavailable() -> None:
    """Đánh dấu NAS lỗi ngay (gọi khi một thao tác NAS thất bại)."""
    cache.set(_REMOTE_CACHE_KEY, False, _REMOTE_TTL_DOWN)


def mount_io_safe(path=None) -> bool:
    """True nếu được phép thao tác I/O trên ``path``.

    Mặc định kiểm tra ``settings.NAS_MOUNT_ROOT``. Trả False chỉ khi đường dẫn
    nằm trên mount FUSE VÀ NAS đang không liên lạc được — tức đúng lúc thao tác
    I/O sẽ treo D-state.
    """
    if path is None:
        path = getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')
    if not path_on_fuse_mount(path):
        return True
    return remote_reachable()


def guard_mount_io(path=None, *, what: str = 'NAS') -> None:
    """Raise OSError nếu chạm mount lúc này sẽ treo worker."""
    if mount_io_safe(path):
        return
    logger.warning('Bỏ qua I/O trên mount FUSE (%s) — NAS đang mất kết nối', what)
    raise OSError(f'NAS đang mất kết nối — bỏ qua truy cập mount ({what}).')


def safe_mount_path(path) -> Path | None:
    """Trả ``Path`` nếu chạm được, None nếu mount đang treo."""
    return Path(path) if mount_io_safe(path) else None
