"""Cache file cài RaiDrive trên đĩa VPS — không đọc mount NAS trong HTTP request."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from django.conf import settings

from nas_storage.nas_paths import _rclone_env, _rclone_remote_path

logger = logging.getLogger(__name__)

_META_SUFFIX = '.meta.json'


def raidrive_cache_dir() -> Path:
    override = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_CACHE_DIR', '').strip()
    if override:
        return Path(override)
    # Docker production: media volume gắn tại /app/media (không phụ thuộc MEDIA_ROOT/BASE_DIR)
    app_media_cache = Path('/app/media/installer-cache')
    if app_media_cache.parent.is_dir():
        return app_media_cache
    return Path(settings.MEDIA_ROOT) / 'installer-cache'


def raidrive_local_override_path() -> Path | None:
    """Đường dẫn cố định trên VPS (nếu IT copy sẵn file — nhanh nhất)."""
    raw = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_LOCAL_PATH', '').strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def _safe_cache_name(filename: str) -> str:
    return (filename or 'RaiDrive-installer.exe').replace('/', '_').replace('\\', '_')


def cache_path_for_filename(filename: str) -> Path:
    return raidrive_cache_dir() / _safe_cache_name(filename)


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_name(cache_path.name + _META_SUFFIX)


def _write_meta(meta_path: Path, *, size: int, mtime: float) -> None:
    meta_path.write_text(
        json.dumps({'size': size, 'mtime': mtime, 'source': 'rclone'}, ensure_ascii=False),
        encoding='utf-8',
    )


def get_ready_raidrive_path(filename: str) -> Path | None:
    """File sẵn sàng trên đĩa VPS — không gọi NAS."""
    local = raidrive_local_override_path()
    if local is not None:
        return local
    cache_path = cache_path_for_filename(filename)
    try:
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            return cache_path
    except OSError:
        return None
    return None


def _sync_via_rclone(rel_path: str, cache_path: Path, meta_path: Path, *, timeout: int) -> Path:
    target = _rclone_remote_path(rel_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + '.tmp')
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    proc = subprocess.run(
        ['rclone', 'copyto', target, str(tmp)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0 or not tmp.is_file():
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(f'Không đồng bộ RaiDrive từ NAS (rclone): {err[:240]}')
    os.replace(tmp, cache_path)
    stat = cache_path.stat()
    _write_meta(meta_path, size=stat.st_size, mtime=stat.st_mtime)
    return cache_path


def sync_raidrive_installer_cache(
    rel_path: str,
    filename: str,
    *,
    force: bool = False,
    timeout: int | None = None,
) -> Path:
    """Đồng bộ qua rclone — chỉ dùng management command hoặc on-demand có timeout ngắn."""
    local = raidrive_local_override_path()
    if local is not None:
        return local

    cache_path = cache_path_for_filename(filename)
    meta_path = _meta_path(cache_path)
    if not force:
        ready = get_ready_raidrive_path(filename)
        if ready is not None:
            return ready

    if timeout is None:
        timeout = int(getattr(settings, 'NAS_RAIDRIVE_CACHE_RCLONE_TIMEOUT', 900) or 900)
    return _sync_via_rclone(rel_path, cache_path, meta_path, timeout=timeout)


def warm_raidrive_installer_cache(*, force: bool = False) -> Path:
    from nas_storage.share_access import get_active_share

    token = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN', '').strip()
    if not token:
        raise ValueError('Chưa cấu hình NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN.')

    share = get_active_share(token)
    if not share or share.is_dir:
        raise ValueError('Share RaiDrive không khả dụng.')

    return sync_raidrive_installer_cache(
        share.rel_path,
        share.item_name or 'RaiDrive-installer.exe',
        force=force,
    )
