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
    """FileSystemStorage trỏ tới thư mục NAS; vẫn đọc/xóa file cũ trong media VPS."""

    def __init__(self):
        # location đọc động qua path() — không bake đường dẫn lúc import model
        super().__init__(location='', base_url=None)

    def path(self, name: str) -> str:
        if is_legacy_weekly_path(name):
            return str(Path(settings.MEDIA_ROOT) / name)
        return str(weekly_report_nas_abs_root() / name)

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
        tmp_path = Path(tempfile.gettempdir()) / f'weekly-upload-{uuid.uuid4().hex}'
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
                folder_rel_base=weekly_report_nas_rel_base(),
                file_rel=name,
            )
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def weekly_attachment_abs_path(att) -> Path | None:
    name = att.file.name
    if not name:
        return None
    path = Path(WeeklyReportNasStorage().path(name))
    try:
        if path.is_file():
            return path
    except OSError:
        pass
    cached = _rclone_cache_path(name)
    if cached.is_file():
        return cached
    try:
        return _rclone_download_to_cache(name)
    except OSError:
        pass
    return _dsm_download_to_cache(name)


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
