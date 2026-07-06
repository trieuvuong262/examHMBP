"""Lưu đính kèm báo cáo tuần trên NAS (Synology qua user tailscale-justplay), không dùng media VPS."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

LEGACY_WEEKLY_PREFIX = 'reports/weekly/'


def weekly_report_nas_rel_base() -> str:
    return (
        getattr(settings, 'NAS_WEEKLY_REPORT_REL_PATH', '')
        or '99_LUU_TRU/1.2026/BAO_CAO_TUAN'
    ).strip('/')


def weekly_report_nas_abs_root() -> Path:
    return Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / weekly_report_nas_rel_base()


def is_legacy_weekly_path(name: str) -> bool:
    return (name or '').startswith(LEGACY_WEEKLY_PREFIX)


def weekly_attachment_upload_to(instance, filename: str) -> str:
    report = instance.report
    week = report.week_start
    week_no = week.isocalendar()[1]
    username = report.employee.username
    safe = get_valid_filename(os.path.basename(filename)) or 'file'
    stem = uuid.uuid4().hex[:12]
    return f'{week.year}/W{week_no:02d}/{username}/{stem}_{safe}'


@deconstructible
class WeeklyReportNasStorage(FileSystemStorage):
    """FileSystemStorage trỏ tới thư mục NAS.

    Khi NAS mất kết nối, file được ghi tạm trên VPS (``reports.nas_pending``)
    và đồng bộ về NAS sau; ``file.name`` luôn là đường dẫn NAS chuẩn.
    """

    def __init__(self):
        # location đọc động qua path() — không bake đường dẫn lúc import model
        super().__init__(location='', base_url=None)

    def path(self, name: str) -> str:
        if is_legacy_weekly_path(name):
            return str(Path(settings.MEDIA_ROOT) / name)
        from reports.nas_pending import KIND_WEEKLY, pending_exists, pending_path

        if pending_exists(KIND_WEEKLY, name):
            return str(pending_path(KIND_WEEKLY, name))
        return str(weekly_report_nas_abs_root() / name)

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        # Tên đã chứa uuid → bỏ qua kiểm tra tồn tại (tránh chạm mount NAS treo).
        return name

    def exists(self, name: str) -> bool:
        from reports.nas_pending import KIND_WEEKLY, pending_exists

        if pending_exists(KIND_WEEKLY, name):
            return True
        try:
            return Path(str(weekly_report_nas_abs_root() / name)).is_file()
        except OSError:
            return False

    def open(self, name: str, mode: str = 'rb'):
        return Path(self.path(name)).open(mode)

    def delete(self, name: str) -> None:
        from reports.nas_pending import KIND_WEEKLY, remove_pending

        remove_pending(KIND_WEEKLY, name)
        path = Path(str(weekly_report_nas_abs_root() / name))
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    def size(self, name: str) -> int:
        return Path(self.path(name)).stat().st_size

    def _save(self, name, content):
        name = self.get_available_name(name)
        tmp_path = Path(tempfile.gettempdir()) / f'weekly-upload-{uuid.uuid4().hex}'
        try:
            with tmp_path.open('wb') as tmp_file:
                if hasattr(content, 'chunks'):
                    for chunk in content.chunks():
                        tmp_file.write(chunk)
                else:
                    tmp_file.write(content.read())

            _persist_weekly_with_fallback(tmp_path, name)
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _persist_weekly_with_fallback(tmp_path: Path, name: str) -> None:
    """Ghi lên NAS; nếu NAS down/lỗi thì lưu tạm VPS để đồng bộ sau."""
    from reports.nas_health import mark_storage_unavailable, report_storage_available
    from reports.nas_pending import KIND_WEEKLY, write_pending

    if report_storage_available():
        from nas_storage.app_nas_storage import persist_app_nas_file

        try:
            persist_app_nas_file(
                tmp_path=tmp_path,
                mount_dest=weekly_report_nas_abs_root() / name.lstrip('/'),
                folder_rel_base=weekly_report_nas_rel_base(),
                file_rel=name,
                allow_mount=False,
            )
            return
        except OSError:
            mark_storage_unavailable()

    write_pending(KIND_WEEKLY, name, tmp_path)


def weekly_attachment_abs_path(att) -> Path | None:
    name = att.file.name
    if not name:
        return None
    return weekly_nas_abs_path(name)


def weekly_nas_abs_path(rel_name: str) -> Path | None:
    if not rel_name:
        return None
    path = Path(WeeklyReportNasStorage().path(rel_name))
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
    full_rel = f'{weekly_report_nas_rel_base()}/{rel_name.lstrip("/")}'
    try:
        return dsm_download_nas_rel(full_rel, cached)
    except DsmUploadError:
        return None


def open_weekly_attachment(att, mode: str = 'rb'):
    path = weekly_attachment_abs_path(att)
    if not path:
        raise FileNotFoundError(att.file.name or 'attachment')
    return path.open(mode)


def _rclone_cache_path(rel_name: str) -> Path:
    safe = rel_name.replace('/', '__').replace('\\', '__')
    return Path(tempfile.gettempdir()) / 'weekly-nas-cache' / safe


def _rclone_download_to_cache(rel_name: str) -> Path:
    cached = _rclone_cache_path(rel_name)
    cached.parent.mkdir(parents=True, exist_ok=True)
    target = _weekly_rclone_target(rel_name)
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


def ensure_weekly_report_nas_dir() -> Path:
    from nas_storage.app_nas_storage import persist_app_nas_mkdir

    root = weekly_report_nas_abs_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        persist_app_nas_mkdir(weekly_report_nas_rel_base())
    return root


def _weekly_rclone_target(rel_name: str) -> str:
    from nas_storage.nas_paths import app_storage_rclone_target

    return app_storage_rclone_target(weekly_report_nas_rel_base(), rel_name.lstrip('/'))


def _rclone_env() -> dict:
    from nas_storage.nas_paths import _rclone_env as nas_rclone_env
    return nas_rclone_env()


def _rclone_mkdir_weekly_root() -> None:
    target = _weekly_rclone_target('')
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
        raise OSError(f'Không tạo được thư mục báo cáo tuần trên NAS: {err[:200]}')


def _rclone_upload_file(local_path: Path, rel_name: str) -> None:
    from nas_storage.app_nas_storage import persist_app_nas_file

    persist_app_nas_file(
        tmp_path=local_path,
        mount_dest=weekly_report_nas_abs_root() / rel_name.lstrip('/'),
        folder_rel_base=weekly_report_nas_rel_base(),
        file_rel=rel_name.lstrip('/'),
    )
