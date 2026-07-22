"""Lưu tài liệu thiết kế hồ sơ SX trên NAS (06_RnD_THIET_KE_SAN_PHAM/0.Portal)."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

LEGACY_DESIGN_PREFIX = 'san_xuat/design/'


def design_nas_rel_base() -> str:
    return (
        getattr(settings, 'NAS_DESIGN_DOC_REL_PATH', '')
        or '06_RnD_THIET_KE_SAN_PHAM/0.Portal'
    ).strip('/')


def design_nas_abs_root() -> Path:
    return Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / design_nas_rel_base()


def is_legacy_design_path(name: str) -> bool:
    return (name or '').startswith(LEGACY_DESIGN_PREFIX)


def _safe_product_folder(product_code: str) -> str:
    raw = (product_code or '').strip() or 'unknown'
    safe = get_valid_filename(raw.replace('/', '-').replace('\\', '-'))
    safe = re.sub(r'[^\w.\-]+', '_', safe, flags=re.UNICODE).strip('._') or 'unknown'
    return safe[:80]


def design_file_upload_to(instance, filename: str) -> str:
    from django.utils import timezone

    tech_doc = getattr(instance, 'tech_doc', None)
    code = getattr(tech_doc, 'product_code', '') if tech_doc else ''
    year = timezone.localdate().year
    if getattr(instance, 'uploaded_at', None):
        year = instance.uploaded_at.year
    safe = get_valid_filename(os.path.basename(filename)) or 'file'
    stem = uuid.uuid4().hex[:12]
    return f'{_safe_product_folder(code)}/{year}/{stem}_{safe}'


@deconstructible
class DesignDocNasStorage(FileSystemStorage):
    """FileSystemStorage trỏ tới thư mục NAS; vẫn đọc/xóa file cũ trong media VPS."""

    def __init__(self):
        super().__init__(location='', base_url=None)

    def path(self, name: str) -> str:
        if is_legacy_design_path(name):
            return str(Path(settings.MEDIA_ROOT) / name)
        return str(design_nas_abs_root() / name)

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
        tmp_path = Path(tempfile.gettempdir()) / f'design-upload-{uuid.uuid4().hex}'
        try:
            with tmp_path.open('wb') as tmp_file:
                if hasattr(content, 'chunks'):
                    for chunk in content.chunks():
                        tmp_file.write(chunk)
                else:
                    tmp_file.write(content.read())

            dest = Path(self.path(name))
            from nas_storage.app_nas_storage import persist_app_nas_file

            persist_app_nas_file(
                tmp_path=tmp_path,
                mount_dest=dest,
                folder_rel_base=design_nas_rel_base(),
                file_rel=name,
            )
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def design_file_abs_path(design_file) -> Path | None:
    name = design_file.file.name if design_file.file else ''
    if not name:
        return None
    path = Path(DesignDocNasStorage().path(name))
    try:
        if path.is_file():
            return path
    except OSError:
        pass
    if is_legacy_design_path(name):
        return None
    cached = _rclone_cache_path(name)
    if cached.is_file():
        return cached
    try:
        return _rclone_download_to_cache(name)
    except OSError:
        pass
    return _dsm_download_to_cache(name)


def open_design_file(design_file, mode: str = 'rb'):
    path = design_file_abs_path(design_file)
    if not path:
        raise FileNotFoundError(design_file.file.name if design_file.file else 'file')
    return path.open(mode)


def _rclone_cache_path(rel_name: str) -> Path:
    safe = rel_name.replace('/', '__').replace('\\', '__')
    return Path(tempfile.gettempdir()) / 'design-nas-cache' / safe


def _rclone_download_to_cache(rel_name: str) -> Path:
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    cached = _rclone_cache_path(rel_name)
    cached.parent.mkdir(parents=True, exist_ok=True)
    target = app_storage_rclone_target(design_nas_rel_base(), rel_name.lstrip('/'))
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


def _dsm_download_to_cache(rel_name: str) -> Path | None:
    from nas_storage.dsm_upload import DsmUploadError, dsm_download_nas_rel

    cached = _rclone_cache_path(rel_name)
    full_rel = f'{design_nas_rel_base()}/{rel_name.lstrip("/")}'
    try:
        return dsm_download_nas_rel(full_rel, cached)
    except DsmUploadError:
        return None
