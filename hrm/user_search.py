"""Tìm kiếm danh sách nhân sự — server-side, qua mọi trang phân trang."""

from django.contrib.auth.models import User
from django.db.models import Q

from PortalJustPlay.list_search import apply_user_search

# Tài khoản quản trị hệ thống — không hiển thị trên danh sách nhân sự
HIDDEN_HRM_LIST_USERNAMES = ('admin',)


def hidden_hrm_username_q(*, user_prefix: str = '') -> Q:
    """Q loại tài khoản hệ thống (admin, …) — `user_prefix` ví dụ `user__`."""
    q = Q()
    for name in HIDDEN_HRM_LIST_USERNAMES:
        q |= Q(**{f'{user_prefix}username__iexact': name})
    return q


def exclude_hidden_hrm_users(queryset):
    return queryset.exclude(hidden_hrm_username_q())


def exclude_hidden_hrm_profiles(queryset):
    return queryset.exclude(hidden_hrm_username_q(user_prefix='user__'))


def filter_users_by_search(queryset, query: str):
    return apply_user_search(queryset, query)


def filter_users_by_department(queryset, department_id: str | None):
    """Lọc theo phòng ban (profile.department_id)."""
    raw = (department_id or '').strip()
    if not raw:
        return queryset
    if raw == 'none':
        return queryset.filter(profile__department__isnull=True)
    if raw.isdigit():
        return queryset.filter(profile__department_id=int(raw))
    return queryset


def user_display_label(user: User) -> str:
    profile = getattr(user, 'profile', None)
    full_name = profile.full_name if profile and profile.full_name else user.get_full_name() or user.username
    code = profile.employee_code if profile and profile.employee_code else '—'
    return f'{full_name} · {code} · {user.username}'
