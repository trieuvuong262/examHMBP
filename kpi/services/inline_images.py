"""Ảnh inline trong Đánh giá thực tế KPI — lưu NAS giống báo cáo VP."""

from __future__ import annotations

import re
from datetime import date

import bleach
from django.contrib.auth import get_user_model
from django.utils.html import escape
from django.utils.safestring import mark_safe

from hrm.concurrent_positions import effective_roles, user_is_director
from hrm.permissions import ROLE_DIRECTOR, SUBORDINATE_MANAGER_ROLES, get_report_team_users
from reports.daily_inline_images import (
    can_view_inline_image as can_view_report_inline_image,
    inline_image_exists,
    is_inline_image_relpath,
    open_inline_image,
    save_inline_image,
)
from reports.daily_nas_storage import OFFICE_MONTH_PREFIX, OFFICE_WEEK_PREFIX

User = get_user_model()

_ALLOWED_TAGS = [
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
    'span', 'div', 'img',
]
_ALLOWED_ATTRIBUTES = {
    '*': ['class'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
}
_ALLOWED_PROTOCOLS = ['http', 'https', 'data']  # data stripped after paste-upload; keep for safety mid-edit


def kpi_image_report_date(*, year: int, month: int) -> date:
    month = max(1, min(12, int(month)))
    return date(int(year), month, 1)


def save_kpi_inline_image(upload, *, username: str, year: int, month: int, ext: str) -> str:
    """Lưu ảnh qua cùng storage/NAS path như báo cáo ngày."""
    return save_inline_image(
        upload,
        username=username,
        report_date=kpi_image_report_date(year=year, month=month),
        ext=ext,
        period=None,
    )


def can_view_kpi_inline_image(viewer, rel: str) -> bool:
    """Cho phép xem nếu có quyền báo cáo tương ứng hoặc xem KPI của chủ ảnh."""
    if can_view_report_inline_image(viewer, rel):
        return True
    if not is_inline_image_relpath(rel) or rel.startswith('reports/ckeditor5/'):
        return False

    stripped = rel
    if stripped.startswith(OFFICE_WEEK_PREFIX):
        stripped = stripped[len(OFFICE_WEEK_PREFIX):]
    elif stripped.startswith(OFFICE_MONTH_PREFIX):
        stripped = stripped[len(OFFICE_MONTH_PREFIX):]

    parts = stripped.split('/')
    if len(parts) < 6:
        return False
    username = parts[2]
    if viewer.username == username:
        return True
    owner = User.objects.filter(username=username).only('pk').first()
    if not owner:
        return False
    if viewer.is_superuser or user_is_director(viewer) or ROLE_DIRECTOR in effective_roles(viewer):
        return True
    from hrm.permissions import get_direct_manager_users, is_global_report_viewer
    if is_global_report_viewer(viewer):
        return True

    # Không xem ảnh trong KPI của cấp trên
    from hrm.models import Profile, ProfileConcurrentPosition
    superior_ids = {m.pk for m in get_direct_manager_users(viewer)}
    superior_ids.update(
        Profile.objects.filter(
            subordinates=viewer, is_employed=True, user__is_active=True,
        ).values_list('user_id', flat=True)
    )
    superior_ids.update(
        ProfileConcurrentPosition.objects.filter(
            is_active=True,
            subordinates=viewer,
            profile__is_employed=True,
            profile__user__is_active=True,
        ).values_list('profile__user_id', flat=True)
    )
    if owner.pk in superior_ids:
        return False

    if effective_roles(viewer) & SUBORDINATE_MANAGER_ROLES:
        return get_report_team_users(viewer).filter(pk=owner.pk).exists()
    return False

def sanitize_actual_html(raw: str | None) -> str:
    """Chuẩn hoá nội dung ô Đánh giá thực tế (text thuần hoặc HTML có ảnh)."""
    text = (raw or '').strip()
    if not text:
        return ''
    if not re.search(r'</?[a-z][\w-]*\b', text, re.IGNORECASE):
        return text
    cleaned = bleach.clean(
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    # Bỏ data: còn sót (ảnh phải upload lên server).
    cleaned = re.sub(
        r'(?i)<img\b[^>]*\bsrc=["\']data:image[^"\']*["\'][^>]*>',
        '',
        cleaned,
    )
    return cleaned.strip()


def render_actual_html(raw: str | None):
    """Hiển thị an toàn trên template."""
    text = (raw or '').strip()
    if not text:
        return '—'
    return actual_html_for_edit(text) or '—'


def actual_html_for_edit(raw: str | None):
    """HTML an toàn để đưa vào contenteditable / lưu form."""
    text = (raw or '').strip()
    if not text:
        return mark_safe('')
    if re.search(r'</?[a-z][\w-]*\b', text, re.IGNORECASE):
        return mark_safe(sanitize_actual_html(text))
    return mark_safe(escape(text).replace('\n', '<br>'))
