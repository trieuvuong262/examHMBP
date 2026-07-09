"""Cache file cài RaiDrive trên đĩa VPS — tránh stream qua mount NAS mỗi lần tải."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

from nas_storage.nas_paths import _rclone_env, _rclone_remote_path

logger = logging.getLogger(__name__)

_META_SUFFIX = '.meta.json'
_COPY_BLOCK = 1024 * 1024


def raidrive_cache_dir() -> Path:
    override = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_CACHE_DIR', '').strip()
    if override:
        return Path(override)
    return Path(settings.MEDIA_ROOT) / 'installer-cache'


def raidrive_local_override_path() -> Path | None:
    """Đường dẫn cố định trên VPS (nếu IT copy sẵn file — nhanh nhất)."""
    raw = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_LOCAL_PATH', '').strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_name(cache_path.name + _META_SUFFIX)


def _read_meta(meta_path: Path) -> dict | None:
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _write_meta(meta_path: Path, *, size: int, mtime: float, source: str) -> None:
    meta_path.write_text(
        json.dumps({'size': size, 'mtime': mtime, 'source': source}, ensure_ascii=False),
        encoding='utf-8',
    )


def _cache_is_fresh(cache_path: Path, meta_path: Path, *, size: int, mtime: float) -> bool:
    if not cache_path.is_file():
        return False
    meta = _read_meta(meta_path)
    if not meta:
        return False
    return meta.get('size') == size and abs(float(meta.get('mtime', 0)) - mtime) < 1


def _copy_file_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + '.tmp')
    try:
        with src.open('rb') as fin, tmp.open('wb') as fout:
            while True:
                chunk = fin.read(_COPY_BLOCK)
                if not chunk:
                    break
                fout.write(chunk)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _sync_via_mount(nas_path: Path, cache_path: Path, meta_path: Path) -> Path:
    _copy_file_atomic(nas_path, cache_path)
    stat = nas_path.stat()
    _write_meta(meta_path, size=stat.st_size, mtime=stat.st_mtime, source='mount')
    return cache_path


def _sync_via_rclone(rel_path: str, cache_path: Path, meta_path: Path) -> Path:
    target = _rclone_remote_path(rel_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + '.tmp')
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    proc = subprocess.run(
        ['rclone', 'copyto', target, str(tmp)],
        capture_output=True,
        text=True,
        timeout=int(getattr(settings, 'NAS_RAIDRIVE_CACHE_RCLONE_TIMEOUT', 900) or 900),
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0 or not tmp.is_file():
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(f'Không đồng bộ RaiDrive từ NAS (rclone): {err[:240]}')
    os.replace(tmp, cache_path)
    stat = cache_path.stat()
    _write_meta(meta_path, size=stat.st_size, mtime=stat.st_mtime, source='rclone')
    return cache_path


def resolve_raidrive_installer_path(
    nas_path: Path,
    *,
    rel_path: str,
    filename: str,
    force_refresh: bool = False,
) -> Path:
    """
  Trả về đường dẫn file trên đĩa VPS để phục vụ tải xuống.
  Lần đầu (hoặc khi file NAS đổi) copy vào MEDIA/installer-cache.
    """
    local = raidrive_local_override_path()
    if local is not None:
        return local

    safe_name = (filename or nas_path.name or 'RaiDrive-installer.exe').replace('/', '_').replace('\\', '_')
    cache_path = raidrive_cache_dir() / safe_name
    meta_path = _meta_path(cache_path)

    if not force_refresh and cache_path.is_file():
        try:
            nas_stat = nas_path.stat()
        except OSError:
            if _read_meta(meta_path):
                logger.warning('NAS RaiDrive không đọc được — dùng cache cũ %s', cache_path)
                return cache_path
            raise
        if _cache_is_fresh(cache_path, meta_path, size=nas_stat.st_size, mtime=nas_stat.st_mtime):
            return cache_path

    try:
        return _sync_via_mount(nas_path, cache_path, meta_path)
    except OSError as mount_exc:
        logger.warning('Cache RaiDrive qua mount thất bại (%s) — thử rclone', mount_exc)
        return _sync_via_rclone(rel_path, cache_path, meta_path)


def warm_raidrive_installer_cache(*, force: bool = False) -> Path:
    from nas_storage.share_access import get_active_share, resolve_path_for_request

    token = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN', '').strip()
    if not token:
        raise ValueError('Chưa cấu hình NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN.')

    local = raidrive_local_override_path()
    if local is not None:
        return local

    share = get_active_share(token)
    if not share or share.is_dir:
        raise ValueError('Share RaiDrive không khả dụng.')

    nas_path = resolve_path_for_request(None, share.rel_path, share=share)
    if not nas_path.is_file():
        raise FileNotFoundError('Không tìm thấy file RaiDrive trên NAS.')

    return resolve_raidrive_installer_path(
        nas_path,
        rel_path=share.rel_path,
        filename=share.item_name,
        force_refresh=force,
    )
