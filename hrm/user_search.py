"""Tìm kiếm danh sách nhân sự — server-side, qua mọi trang phân trang."""

from django.contrib.auth.models import User

from PortalJustPlay.list_search import apply_user_search


def filter_users_by_search(queryset, query: str):
    return apply_user_search(queryset, query)


def user_display_label(user: User) -> str:
    profile = getattr(user, 'profile', None)
    full_name = profile.full_name if profile and profile.full_name else user.get_full_name() or user.username
    code = profile.employee_code if profile and profile.employee_code else '—'
    return f'{full_name} · {code} · {user.username}'
