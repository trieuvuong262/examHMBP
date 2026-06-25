"""Ảnh inline CKEditor trong báo cáo ngày VP — lưu NAS, không dùng media VPS."""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.utils import timezone

from hrm.permissions import get_report_team_users, is_global_report_viewer
from reports.daily_nas_storage import DailyReportNasStorage, daily_nas_abs_path, open_daily_nas_file

User = get_user_model()

LEGACY_CKEDITOR_PREFIX = 'reports/ckeditor5/'
INLINE_SEGMENT = '/vanban/inline/'
INLINE_REL_PATTERN = re.compile(
    r'^\d{4}/\d{4}-\d{2}-\d{2}/[^/]+/vanban/inline/[^/]+$',
)


def parse_upload_report_date(request) -> date:
    raw = (
        request.POST.get('report_date')
        or request.GET.get('report_date')
        or ''
    ).strip()[:10]
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


def inline_image_upload_rel(username: str, report_date: date, ext: str) -> str:
    safe_ext = ext if ext.startswith('.') else f'.{ext}'
    stem = uuid.uuid4().hex
    return (
        f'{report_date.year}/{report_date.isoformat()}/{username}/vanban/inline/'
        f'{stem}{safe_ext}'
    )


def is_inline_image_relpath(rel: str) -> bool:
    if not rel or '..' in rel:
        return False
    if rel.startswith(LEGACY_CKEDITOR_PREFIX):
        return True
    return bool(INLINE_REL_PATTERN.match(rel))


def inline_image_relpath_from_url(url: str) -> str | None:
    if not url:
        return None
    from reports.office_content import _ckeditor_relpath_from_url

    legacy = _ckeditor_relpath_from_url(url)
    if legacy:
        return legacy

    from urllib.parse import unquote, urlparse

    raw = unquote(url.strip())
    path = urlparse(raw).path or raw

    doc_marker = '/reports/doc-image/'
    if doc_marker in path:
        tail = path.split(doc_marker, 1)[1].lstrip('/')
        parts = tail.split('/', 1)
        rel = parts[1] if len(parts) == 2 and parts[0].isdigit() else tail
        if is_inline_image_relpath(rel):
            return rel

    inline_marker = '/reports/inline-image/'
    if inline_marker in path:
        rel = path.split(inline_marker, 1)[1].lstrip('/').split('?', 1)[0]
        if is_inline_image_relpath(rel):
            return rel

    rel = path.lstrip('/')
    if is_inline_image_relpath(rel):
        return rel
    return None


def can_view_inline_image(viewer, rel: str) -> bool:
    if not is_inline_image_relpath(rel):
        return False
    if rel.startswith(LEGACY_CKEDITOR_PREFIX):
        return True

    parts = rel.split('/')
    if len(parts) < 6:
        return False
    username = parts[2]
    if viewer.username == username:
        return True
    owner = User.objects.filter(username=username).only('pk').first()
    if not owner:
        return False
    if is_global_report_viewer(viewer):
        from hrm.module_permissions import MODULE_REPORTS
        from hrm.role_permissions import user_can_view_module
        return user_can_view_module(viewer, MODULE_REPORTS)
    return get_report_team_users(viewer).filter(pk=owner.pk).exists()


def save_inline_image(upload, *, username: str, report_date: date, ext: str) -> str:
    rel = inline_image_upload_rel(username, report_date, ext)
    DailyReportNasStorage().save(rel, upload)
    return rel


def open_inline_image(rel: str, mode: str = 'rb'):
    if rel.startswith(LEGACY_CKEDITOR_PREFIX):
        from django.core.files.storage import default_storage

        if not default_storage.exists(rel):
            raise FileNotFoundError(rel)
        return default_storage.open(rel, mode)
    return open_daily_nas_file(rel, mode=mode)


def inline_image_exists(rel: str) -> bool:
    if rel.startswith(LEGACY_CKEDITOR_PREFIX):
        from django.core.files.storage import default_storage

        return default_storage.exists(rel)
    return daily_nas_abs_path(rel) is not None
