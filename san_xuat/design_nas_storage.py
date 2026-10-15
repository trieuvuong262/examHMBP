"""Lưu tài liệu thiết kế hồ sơ SX trên NAS (06_RnD_THIET_KE_SAN_PHAM/0.Portal)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

LEGACY_DESIGN_PREFIX = 'san_xuat/design/'
LEGACY_LIBRARY_PREFIX = 'kho_sp/'
_PENDING_DIRNAME = 'design_pending'


def design_nas_rel_base() -> str:
    return (
        getattr(settings, 'NAS_DESIGN_DOC_REL_PATH', '')
        or '06_RnD_THIET_KE_SAN_PHAM/0.Portal'
    ).strip('/')


def design_nas_abs_root() -> Path:
    return Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / design_nas_rel_base()


def _rel(name: str) -> str:
    return (name or '').replace('\\', '/').lstrip('/')


def is_legacy_design_path(name: str) -> bool:
    return _rel(name).startswith(LEGACY_DESIGN_PREFIX)


def is_legacy_media_path(name: str) -> bool:
    """File tạo trước khi ghi NAS — vẫn nằm trong MEDIA_ROOT."""
    name = _rel(name)
    return name.startswith(LEGACY_DESIGN_PREFIX) or name.startswith(LEGACY_LIBRARY_PREFIX)


def pending_root() -> Path:
    return Path(settings.MEDIA_ROOT) / _PENDING_DIRNAME


def pending_path(name: str) -> Path:
    return pending_root() / _rel(name)


def pending_exists(name: str) -> bool:
    if not name or is_legacy_media_path(name):
        return False
    try:
        return pending_path(name).is_file()
    except OSError:
        return False


def write_pending(name: str, tmp_path: Path) -> Path:
    dest = pending_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_path, dest)
    return dest


def remove_pending(name: str) -> None:
    dest = pending_path(name)
    try:
        dest.unlink(missing_ok=True)
    except OSError:
        return
    root = pending_root()
    parent = dest.parent
    while parent != root and parent.is_relative_to(root):
        try:
            next(parent.iterdir())
            break
        except StopIteration:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        except OSError:
            break


def iter_pending_design_names():
    root = pending_root()
    if not root.exists():
        return
    for path in root.rglob('*'):
        try:
            if path.is_file():
                yield path.relative_to(root).as_posix()
        except OSError:
            continue


def has_pending_design() -> bool:
    for _name in iter_pending_design_names():
        return True
    return False


def upload_pending_design(name: str) -> None:
    """Đẩy một file tạm lên NAS rồi xóa bản tạm."""
    from nas_storage.app_nas_storage import persist_app_nas_file

    src = pending_path(name)
    if not src.is_file():
        return
    persist_app_nas_file(
        tmp_path=src,
        mount_dest=design_nas_abs_root() / _rel(name),
        folder_rel_base=design_nas_rel_base(),
        file_rel=_rel(name),
        allow_mount=False,
    )
    remove_pending(name)


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

    def generate_filename(self, filename: str) -> str:
        return super().generate_filename(filename).replace('\\', '/')

    def path(self, name: str) -> str:
        name = _rel(name)
        if is_legacy_media_path(name):
            return str(Path(settings.MEDIA_ROOT) / name)
        if pending_exists(name):
            return str(pending_path(name))
        return str(design_nas_abs_root() / name)

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        # Tên đã chứa uuid → không kiểm tra tồn tại (tránh chạm mount NAS treo).
        return _rel(name)

    def exists(self, name: str) -> bool:
        name = _rel(name)
        if is_legacy_media_path(name):
            try:
                return (Path(settings.MEDIA_ROOT) / name).is_file()
            except OSError:
                return False
        if pending_exists(name):
            return True
        from nas_storage.nas_mount_health import mount_io_safe

        path = design_nas_abs_root() / name
        if not mount_io_safe(path):
            return False
        try:
            return path.is_file()
        except OSError:
            return False

    def open(self, name: str, mode: str = 'rb'):
        path = design_file_abs_path(_rel(name))
        if not path:
            raise FileNotFoundError(name or 'file')
        return path.open(mode)

    def delete(self, name: str) -> None:
        name = _rel(name)
        if not name:
            return
        if is_legacy_media_path(name):
            try:
                (Path(settings.MEDIA_ROOT) / name).unlink(missing_ok=True)
            except OSError:
                pass
            return
        remove_pending(name)
        cache = _rclone_cache_path(name)
        try:
            cache.unlink(missing_ok=True)
        except OSError:
            pass
        from nas_storage.nas_mount_health import mount_io_safe

        path = design_nas_abs_root() / name
        if mount_io_safe(path):
            try:
                if path.is_file():
                    path.unlink()
                    return
            except OSError:
                pass
        _rclone_delete(name)

    def size(self, name: str) -> int:
        path = design_file_abs_path(_rel(name))
        if not path:
            raise FileNotFoundError(name or 'file')
        return path.stat().st_size

    def url(self, name: str) -> str:
        name = _rel(name)
        if not name:
            return ''
        try:
            from django.urls import reverse

            if name.startswith(LEGACY_LIBRARY_PREFIX) or name.startswith('thu_vien/'):
                from kho_san_pham.models import Product

                pk = Product.objects.filter(image=name).values_list('pk', flat=True).first()
                if pk:
                    return reverse('kho_san_pham:product_image', args=[pk])
            if name.startswith('thiet_ke_sp/') or name.startswith('Thiết Kế Sản Phẩm/'):
                from thiet_ke_sp.models import Attachment

                pk = Attachment.objects.filter(file=name).values_list('pk', flat=True).first()
                if pk:
                    return reverse('thiet_ke_sp:attachment_serve', args=[pk])
        except Exception:
            return ''
        return ''

    def _save(self, name, content):
        name = _rel(self.get_available_name(name))
        tmp_path = Path(tempfile.gettempdir()) / f'design-upload-{uuid.uuid4().hex}'
        try:
            with tmp_path.open('wb') as tmp_file:
                if hasattr(content, 'chunks'):
                    for chunk in content.chunks():
                        tmp_file.write(chunk)
                else:
                    tmp_file.write(content.read())
            _persist_design_with_fallback(tmp_path, name)
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _persist_design_with_fallback(tmp_path: Path, name: str) -> None:
    """Ghi lên NAS; NAS down thì lưu tạm VPS (cùng cách đính kèm báo cáo VP)."""
    from nas_storage.app_nas_storage import persist_app_nas_file
    from reports.nas_health import mark_storage_unavailable, report_storage_available

    name = _rel(name)
    if report_storage_available():
        try:
            persist_app_nas_file(
                tmp_path=tmp_path,
                mount_dest=design_nas_abs_root() / name,
                folder_rel_base=design_nas_rel_base(),
                file_rel=name,
                allow_mount=False,
            )
            return
        except OSError:
            mark_storage_unavailable()
    write_pending(name, tmp_path)


def _stored_name(source) -> str:
    if isinstance(source, str):
        return _rel(source)
    field = getattr(source, 'file', None) or getattr(source, 'image', None)
    return _rel(field.name if field else '')


def design_file_abs_path(design_file) -> Path | None:
    name = _stored_name(design_file)
    if not name:
        return None
    if is_legacy_media_path(name):
        path = Path(settings.MEDIA_ROOT) / name
        try:
            return path if path.is_file() else None
        except OSError:
            return None
    if pending_exists(name):
        return pending_path(name)
    from nas_storage.nas_mount_health import mount_io_safe

    path = design_nas_abs_root() / name
    if mount_io_safe(path):
        try:
            if path.is_file():
                return path
        except OSError:
            pass
    cached = _rclone_cache_path(name)
    try:
        if cached.is_file():
            return cached
    except OSError:
        pass
    try:
        return _rclone_download_to_cache(name)
    except OSError:
        pass
    return _dsm_download_to_cache(name)


def open_design_file(design_file, mode: str = 'rb'):
    path = design_file_abs_path(design_file)
    if not path:
        raise FileNotFoundError(_stored_name(design_file) or 'file')
    return path.open(mode)


def _rclone_delete(rel_name: str) -> None:
    from nas_storage.app_nas_storage import rclone_request_timeout
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    target = app_storage_rclone_target(design_nas_rel_base(), _rel(rel_name))
    try:
        subprocess.run(
            [
                'rclone', 'deletefile', target,
                '--contimeout', '5s', '--timeout', '30s', '--retries', '1', '--low-level-retries', '1',
            ],
            capture_output=True,
            text=True,
            timeout=min(90, rclone_request_timeout()),
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _rclone_cache_path(rel_name: str) -> Path:
    safe = rel_name.replace('/', '__').replace('\\', '__')
    return Path(tempfile.gettempdir()) / 'design-nas-cache' / safe


def _rclone_download_to_cache(rel_name: str) -> Path:
    from nas_storage.app_nas_storage import rclone_request_timeout
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    cached = _rclone_cache_path(rel_name)
    cached.parent.mkdir(parents=True, exist_ok=True)
    target = app_storage_rclone_target(design_nas_rel_base(), rel_name.lstrip('/'))
    proc = subprocess.run(
        ['rclone', 'copyto', target, str(cached)],
        capture_output=True,
        text=True,
        timeout=rclone_request_timeout(),
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
