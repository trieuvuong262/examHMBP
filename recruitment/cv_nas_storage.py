"""Lưu CV / hồ sơ ứng viên trên NAS, cùng cách báo cáo VP.

Thư mục NAS (ổ JustPlayNAS):
``02_HANH_CHINH_NHAN_SU/1.P.HCNS - Folder_Dung_Chung/14.Portal - CV``

File mới ghi thẳng lên NAS (rclone/DSM, không chạm mount FUSE). NAS mất kết nối
thì lưu tạm trên VPS; ``file.name`` vẫn là đường dẫn NAS để đồng bộ sau chỉ là
đẩy file + xóa bản tạm. File cũ ``cv/...`` vẫn đọc từ kho riêng tư trên VPS.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

# Hồ sơ tạo trước khi chuyển NAS — nằm ở MEDIA_ROOT/_private/recruitment/.
LEGACY_CV_PREFIX = 'cv/'
_PENDING_DIRNAME = 'recruitment_pending'


def cv_nas_rel_base() -> str:
    return (
        getattr(settings, 'NAS_RECRUITMENT_CV_REL_PATH', '')
        or '02_HANH_CHINH_NHAN_SU/1.P.HCNS - Folder_Dung_Chung/14.Portal - CV'
    ).strip().strip('/')


def cv_nas_abs_root() -> Path:
    return Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / cv_nas_rel_base()


def _rel(name: str) -> str:
    """Đường dẫn lưu trong DB luôn dùng dấu / — Windows normpath đổi thành \\."""
    return (name or '').replace('\\', '/').lstrip('/')


def is_legacy_cv_path(name: str) -> bool:
    return _rel(name).startswith(LEGACY_CV_PREFIX)


def legacy_cv_abs_path(name: str) -> Path:
    return Path(settings.MEDIA_ROOT) / '_private' / 'recruitment' / _rel(name)


def _safe_filename(filename: str, fallback: str) -> str:
    try:
        safe = get_valid_filename(os.path.basename(filename or ''))
    except SuspiciousFileOperation:
        safe = ''
    return safe or fallback


def cv_upload_to(instance, filename: str) -> str:
    """``2026/10/36_Nguyen_Van_A/abc123_ho_so.pdf`` trong thư mục CV trên NAS."""
    candidate = instance.candidate
    when = timezone.localdate()
    person = _safe_filename(getattr(candidate, 'full_name', '') or '', 'ung-vien')[:60]
    safe = _safe_filename(filename, 'cv')
    stem = uuid.uuid4().hex[:12]
    prefix = f'{when:%Y/%m}/{candidate.pk or 0}_{person}/{stem}_'
    room = 240 - len(prefix)
    if len(safe) > room:
        ext = os.path.splitext(safe)[1][:10]
        safe = (safe[: max(1, room - len(ext))] + ext)[:room]
    return f'{prefix}{safe}'


def pending_root() -> Path:
    return Path(settings.MEDIA_ROOT) / _PENDING_DIRNAME


def pending_path(name: str) -> Path:
    return pending_root() / _rel(name)


def pending_exists(name: str) -> bool:
    if not name or is_legacy_cv_path(name):
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


def iter_pending_cv_names():
    root = pending_root()
    if not root.exists():
        return
    for path in root.rglob('*'):
        try:
            if path.is_file():
                yield path.relative_to(root).as_posix()
        except OSError:
            continue


def count_pending_cv() -> int:
    return sum(1 for _ in iter_pending_cv_names())


def has_pending_cv() -> bool:
    for _ in iter_pending_cv_names():
        return True
    return False


def upload_pending_cv(name: str) -> None:
    """Đẩy một CV tạm lên NAS rồi xóa bản tạm. Raise OSError nếu NAS không nhận."""
    from nas_storage.app_nas_storage import persist_app_nas_file

    src = pending_path(name)
    if not src.is_file():
        return
    persist_app_nas_file(
        tmp_path=src,
        mount_dest=cv_nas_abs_root() / name.lstrip('/'),
        folder_rel_base=cv_nas_rel_base(),
        file_rel=name.lstrip('/'),
        allow_mount=False,
    )
    remove_pending(name)


@deconstructible
class CandidateCvNasStorage(FileSystemStorage):
    """CV trên NAS. Không có URL công khai — xem qua view ``recruitment_file``."""

    def __init__(self):
        super().__init__(location='', base_url=None)

    def generate_filename(self, filename: str) -> str:
        return super().generate_filename(filename).replace('\\', '/')

    def path(self, name: str) -> str:
        name = _rel(name)
        if is_legacy_cv_path(name):
            return str(legacy_cv_abs_path(name))
        if pending_exists(name):
            return str(pending_path(name))
        return str(cv_nas_abs_root() / name)

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        # Tên đã chứa uuid → không kiểm tra tồn tại (tránh chạm mount NAS treo).
        return name

    def exists(self, name: str) -> bool:
        name = _rel(name)
        if is_legacy_cv_path(name):
            try:
                return legacy_cv_abs_path(name).is_file()
            except OSError:
                return False
        if pending_exists(name):
            return True
        from nas_storage.nas_mount_health import mount_io_safe

        path = cv_nas_abs_root() / name
        if not mount_io_safe(path):
            return False
        try:
            return path.is_file()
        except OSError:
            return False

    def open(self, name: str, mode: str = 'rb'):
        path = cv_abs_path(_rel(name))
        if not path:
            raise FileNotFoundError(name or 'cv')
        return path.open(mode)

    def delete(self, name: str) -> None:
        name = _rel(name)
        if not name:
            return
        if is_legacy_cv_path(name):
            try:
                legacy_cv_abs_path(name).unlink(missing_ok=True)
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

        path = cv_nas_abs_root() / name
        if mount_io_safe(path):
            try:
                if path.is_file():
                    path.unlink()
                    return
            except OSError:
                pass
        _rclone_delete(name)

    def size(self, name: str) -> int:
        path = cv_abs_path(_rel(name))
        if not path:
            raise FileNotFoundError(name or 'cv')
        return path.stat().st_size

    def _save(self, name, content):
        name = _rel(self.get_available_name(name))
        tmp_path = Path(tempfile.gettempdir()) / f'cv-upload-{uuid.uuid4().hex}'
        try:
            with tmp_path.open('wb') as tmp_file:
                if hasattr(content, 'chunks'):
                    for chunk in content.chunks():
                        tmp_file.write(chunk)
                else:
                    tmp_file.write(content.read())
            _persist_cv_with_fallback(tmp_path, name)
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _persist_cv_with_fallback(tmp_path: Path, name: str) -> None:
    """Ghi lên NAS; NAS down thì lưu tạm VPS (giống đính kèm báo cáo VP)."""
    from nas_storage.app_nas_storage import persist_app_nas_file
    from reports.nas_health import mark_storage_unavailable, report_storage_available

    if report_storage_available():
        try:
            persist_app_nas_file(
                tmp_path=tmp_path,
                mount_dest=cv_nas_abs_root() / name.lstrip('/'),
                folder_rel_base=cv_nas_rel_base(),
                file_rel=name.lstrip('/'),
                allow_mount=False,
            )
            return
        except OSError:
            mark_storage_unavailable()
    write_pending(name, tmp_path)


def cv_abs_path(rel_name: str) -> Path | None:
    rel_name = _rel(rel_name)
    if not rel_name:
        return None
    if is_legacy_cv_path(rel_name):
        path = legacy_cv_abs_path(rel_name)
        try:
            return path if path.is_file() else None
        except OSError:
            return None
    if pending_exists(rel_name):
        return pending_path(rel_name)
    from nas_storage.nas_mount_health import mount_io_safe

    path = cv_nas_abs_root() / rel_name
    if mount_io_safe(path):
        try:
            if path.is_file():
                return path
        except OSError:
            pass
    cached = _rclone_cache_path(rel_name)
    if cached.is_file():
        return cached
    try:
        return _rclone_download_to_cache(rel_name)
    except OSError:
        pass
    return _dsm_download_to_cache(rel_name)


def _dsm_download_to_cache(rel_name: str) -> Path | None:
    from nas_storage.dsm_upload import DsmUploadError, dsm_download_nas_rel

    cached = _rclone_cache_path(rel_name)
    full_rel = f'{cv_nas_rel_base()}/{rel_name.lstrip("/")}'
    try:
        return dsm_download_nas_rel(full_rel, cached)
    except DsmUploadError:
        return None


def _rclone_cache_path(rel_name: str) -> Path:
    safe = rel_name.replace('/', '__').replace('\\', '__')
    return Path(tempfile.gettempdir()) / 'cv-nas-cache' / safe


def _rclone_download_to_cache(rel_name: str) -> Path:
    from nas_storage.app_nas_storage import rclone_request_timeout
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    cached = _rclone_cache_path(rel_name)
    cached.parent.mkdir(parents=True, exist_ok=True)
    target = app_storage_rclone_target(cv_nas_rel_base(), rel_name.lstrip('/'))
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
        raise OSError(f'Không tải được CV từ NAS: {err[:200]}')
    return cached


def _rclone_delete(rel_name: str) -> None:
    from nas_storage.app_nas_storage import rclone_request_timeout
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    target = app_storage_rclone_target(cv_nas_rel_base(), rel_name.lstrip('/'))
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
