"""Lưu file thông báo trên NAS (99_LUU_TRU/1.2026/THONG_BAO), không dùng media VPS."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

LEGACY_ANNOUNCEMENT_PREFIXES = (
    'announcements/pdf/',
    'announcements/videos/',
)

ANNOUNCEMENT_FILE_FIELDS = frozenset({'pdf_file', 'video_file', 'original_file'})


def announcement_nas_rel_base() -> str:
    return (
        getattr(settings, 'NAS_ANNOUNCEMENT_REL_PATH', '')
        or '99_LUU_TRU/1.2026/THONG_BAO'
    ).strip('/')


def announcement_nas_abs_root() -> Path:
    return Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / announcement_nas_rel_base()


def is_legacy_announcement_path(name: str) -> bool:
    name = name or ''
    return any(name.startswith(prefix) for prefix in LEGACY_ANNOUNCEMENT_PREFIXES)


def announcement_file_upload_to(instance, filename: str) -> str:
    from django.utils import timezone

    year = instance.created_at.year if instance.created_at else timezone.localdate().year
    pk = instance.pk or 0
    safe = get_valid_filename(os.path.basename(filename)) or 'file'
    stem = uuid.uuid4().hex[:12]
    return f'{year}/{pk}/{stem}_{safe}'


@deconstructible
class AnnouncementNasStorage(FileSystemStorage):
    """FileSystemStorage trỏ tới thư mục NAS; vẫn đọc/xóa file cũ trong media VPS."""

    def __init__(self):
        super().__init__(location='', base_url=None)

    def path(self, name: str) -> str:
        if is_legacy_announcement_path(name):
            return str(Path(settings.MEDIA_ROOT) / name)
        return str(announcement_nas_abs_root() / name)

    def exists(self, name: str) -> bool:
        try:
            return Path(self.path(name)).is_file()
        except OSError:
            return False

    def open(self, name: str, mode: str = 'rb'):
        return Path(self.path(name)).open(mode)

    def delete(self, name: str) -> None:
        path = Path(self.path(name))
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    def size(self, name: str) -> int:
        return Path(self.path(name)).stat().st_size

    def _save(self, name, content):
        name = self.get_available_name(name)
        tmp_path = Path(tempfile.gettempdir()) / f'announcement-upload-{uuid.uuid4().hex}'
        try:
            with tmp_path.open('wb') as tmp_file:
                if hasattr(content, 'chunks'):
                    for chunk in content.chunks():
                        tmp_file.write(chunk)
                else:
                    tmp_file.write(content.read())

            dest = Path(self.path(name))
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(tmp_path, dest)
            except OSError:
                _rclone_upload_file(tmp_path, name)
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def announcement_file_abs_path(announcement, field_name: str) -> Path | None:
    if field_name not in ANNOUNCEMENT_FILE_FIELDS:
        return None
    field = getattr(announcement, field_name, None)
    name = field.name if field else ''
    if not name:
        return None
    path = Path(AnnouncementNasStorage().path(name))
    if path.is_file():
        return path
    cached = _rclone_cache_path(name)
    if cached.is_file():
        return cached
    try:
        return _rclone_download_to_cache(name)
    except OSError:
        return None


def open_announcement_file(announcement, field_name: str, mode: str = 'rb'):
    path = announcement_file_abs_path(announcement, field_name)
    if not path:
        field = getattr(announcement, field_name, None)
        raise FileNotFoundError(field.name if field else field_name)
    return path.open(mode)


def _rclone_cache_path(rel_name: str) -> Path:
    safe = rel_name.replace('/', '__').replace('\\', '__')
    return Path(tempfile.gettempdir()) / 'announcement-nas-cache' / safe


def _rclone_download_to_cache(rel_name: str) -> Path:
    cached = _rclone_cache_path(rel_name)
    cached.parent.mkdir(parents=True, exist_ok=True)
    target = _announcement_rclone_target(rel_name)
    proc = subprocess.run(
        ['rclone', 'copyto', target, str(cached)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0 or not cached.is_file():
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(f'Không tải được file từ NAS: {err[:200]}')
    return cached


def ensure_announcement_nas_dir() -> Path:
    root = announcement_nas_abs_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        _rclone_mkdir_announcement_root()
    return root


def _announcement_rclone_target(rel_name: str) -> str:
    from nas_storage.nas_paths import default_nas_rclone_remote, nas_rclone_remote_path

    folder = announcement_nas_rel_base()
    rel = rel_name.lstrip('/')
    if folder and rel:
        return nas_rclone_remote_path(default_nas_rclone_remote(), f'{folder}/{rel}')
    if folder:
        return nas_rclone_remote_path(default_nas_rclone_remote(), folder)
    return nas_rclone_remote_path(default_nas_rclone_remote(), rel)


def _rclone_env() -> dict:
    from nas_storage.nas_paths import _rclone_env as nas_rclone_env
    return nas_rclone_env()


def _rclone_mkdir_announcement_root() -> None:
    target = _announcement_rclone_target('')
    proc = subprocess.run(
        ['rclone', 'mkdir', target.rstrip('/')],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(f'Không tạo được thư mục thông báo trên NAS: {err[:200]}')


def _rclone_upload_file(local_path: Path, rel_name: str) -> None:
    target = _announcement_rclone_target(rel_name)
    proc = subprocess.run(
        ['rclone', 'copyto', str(local_path), target],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(f'Không ghi được file lên NAS: {err[:200]}')
