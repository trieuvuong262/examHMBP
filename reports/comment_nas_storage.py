"""Lưu đính kèm nhận xét báo cáo trên NAS — theo thư mục báo cáo ngày/tuần."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

from reports.daily_nas_storage import daily_report_nas_abs_root, daily_report_nas_rel_base
from reports.weekly_nas_storage import weekly_report_nas_abs_root, weekly_report_nas_rel_base

DAILY_PREFIX = 'd/'
WEEKLY_PREFIX = 'w/'


def _comment_rel_suffix(comment, filename: str) -> str:
    safe = get_valid_filename(os.path.basename(filename)) or 'file'
    stem = uuid.uuid4().hex[:12]
    name = f'{stem}_{safe}'
    if comment.daily_report_id:
        report = comment.daily_report
        return (
            f'{report.report_date.year}/{report.report_date.isoformat()}/'
            f'{report.employee.username}/comments/{name}'
        )
    report = comment.weekly_report
    week = report.week_start
    week_no = week.isocalendar()[1]
    return f'{week.year}/W{week_no:02d}/{report.employee.username}/comments/{name}'


def comment_attachment_upload_to(instance, filename: str) -> str:
    comment = instance.comment
    rel = _comment_rel_suffix(comment, filename)
    if comment.daily_report_id:
        return f'{DAILY_PREFIX}{rel}'
    return f'{WEEKLY_PREFIX}{rel}'


def _folder_rel_base(name: str) -> str:
    if name.startswith(DAILY_PREFIX):
        return daily_report_nas_rel_base()
    if name.startswith(WEEKLY_PREFIX):
        return weekly_report_nas_rel_base()
    return daily_report_nas_rel_base()


def _rel_without_prefix(name: str) -> str:
    if name.startswith(DAILY_PREFIX):
        return name[len(DAILY_PREFIX):]
    if name.startswith(WEEKLY_PREFIX):
        return name[len(WEEKLY_PREFIX):]
    return name.lstrip('/')


def _abs_root(name: str) -> Path:
    if name.startswith(WEEKLY_PREFIX):
        return weekly_report_nas_abs_root()
    return daily_report_nas_abs_root()


def _kind_for(name: str) -> str:
    from reports.nas_pending import KIND_DAILY, KIND_WEEKLY

    return KIND_WEEKLY if name.startswith(WEEKLY_PREFIX) else KIND_DAILY


@deconstructible
class ReportCommentNasStorage(FileSystemStorage):
    """Đính kèm nhận xét — cùng thư mục NAS báo cáo ngày/tuần.

    Khi NAS mất kết nối, file lưu tạm trên VPS (dùng chung ``reports.nas_pending``
    theo kind daily/weekly) và tự đồng bộ về NAS sau.
    """

    def __init__(self):
        super().__init__(location='', base_url=None)

    def path(self, name: str) -> str:
        from reports.nas_pending import pending_exists, pending_path

        kind = _kind_for(name)
        rel = _rel_without_prefix(name)
        if pending_exists(kind, rel):
            return str(pending_path(kind, rel))
        return str(_abs_root(name) / rel)

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        return name

    def exists(self, name: str) -> bool:
        from reports.nas_pending import pending_exists

        kind = _kind_for(name)
        rel = _rel_without_prefix(name)
        if pending_exists(kind, rel):
            return True
        try:
            return Path(str(_abs_root(name) / rel)).is_file()
        except OSError:
            return False

    def open(self, name: str, mode: str = 'rb'):
        return Path(self.path(name)).open(mode)

    def delete(self, name: str) -> None:
        from reports.nas_pending import remove_pending

        remove_pending(_kind_for(name), _rel_without_prefix(name))
        path = Path(str(_abs_root(name) / _rel_without_prefix(name)))
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    def size(self, name: str) -> int:
        return Path(self.path(name)).stat().st_size

    def _save(self, name, content):
        name = self.get_available_name(name)
        tmp_path = Path(tempfile.gettempdir()) / f'comment-upload-{uuid.uuid4().hex}'
        try:
            with tmp_path.open('wb') as tmp_file:
                if hasattr(content, 'chunks'):
                    for chunk in content.chunks():
                        tmp_file.write(chunk)
                else:
                    tmp_file.write(content.read())

            _persist_comment_with_fallback(tmp_path, name)
            return name
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _persist_comment_with_fallback(tmp_path: Path, name: str) -> None:
    """Ghi lên NAS; nếu NAS down/lỗi thì lưu tạm VPS để đồng bộ sau."""
    from reports.nas_health import mark_storage_unavailable, report_storage_available
    from reports.nas_pending import write_pending

    kind = _kind_for(name)
    rel = _rel_without_prefix(name)

    if report_storage_available():
        from nas_storage.app_nas_storage import persist_app_nas_file

        try:
            persist_app_nas_file(
                tmp_path=tmp_path,
                mount_dest=_abs_root(name) / rel,
                folder_rel_base=_folder_rel_base(name),
                file_rel=rel,
                allow_mount=False,
            )
            return
        except OSError:
            mark_storage_unavailable()

    write_pending(kind, rel, tmp_path)


def comment_attachment_abs_path(att) -> Path | None:
    name = att.file.name
    if not name:
        return None
    if name.startswith(DAILY_PREFIX):
        from reports.daily_nas_storage import daily_nas_abs_path

        return daily_nas_abs_path(_rel_without_prefix(name))
    if name.startswith(WEEKLY_PREFIX):
        from reports.weekly_nas_storage import weekly_nas_abs_path

        return weekly_nas_abs_path(_rel_without_prefix(name))
    path = Path(ReportCommentNasStorage().path(name))
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def open_comment_attachment(att, mode: str = 'rb'):
    path = comment_attachment_abs_path(att)
    if not path:
        raise FileNotFoundError(att.file.name or 'comment-attachment')
    return path.open(mode)
