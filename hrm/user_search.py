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


def visible_employed_profiles(**filters):
    """Hồ sơ NV đang làm việc, không tính tài khoản hệ thống (admin)."""
    from hrm.models import Profile

    return exclude_hidden_hrm_profiles(Profile.objects.filter(is_employed=True, **filters))


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


def filter_users_by_division(queryset, division_id: str | None):
    """Lọc theo bộ phận (profile.division_id)."""
    raw = (division_id or '').strip()
    if not raw:
        return queryset
    if raw == 'none':
        return queryset.filter(profile__division__isnull=True)
    if raw.isdigit():
        return queryset.filter(profile__division_id=int(raw))
    return queryset


def filter_users_by_job_position(queryset, job_position: str | None):
    """Lọc theo vị trí (profile.job_position, khớp không phân biệt hoa thường)."""
    raw = (job_position or '').strip()
    if not raw:
        return queryset
    if raw == 'none':
        return queryset.filter(
            Q(profile__job_position='') | Q(profile__job_position__isnull=True),
        )
    return queryset.filter(profile__job_position__iexact=raw)


def distinct_job_positions_for_filter(
    *,
    department_id: str = '',
    division_id: str = '',
) -> list[str]:
    """Danh sách vị trí (distinct) cho dropdown lọc nhân sự."""
    qs = visible_employed_profiles()
    dept_raw = (department_id or '').strip()
    if dept_raw == 'none':
        qs = qs.filter(department__isnull=True)
    elif dept_raw.isdigit():
        qs = qs.filter(department_id=int(dept_raw))
    div_raw = (division_id or '').strip()
    if div_raw == 'none':
        qs = qs.filter(division__isnull=True)
    elif div_raw.isdigit():
        qs = qs.filter(division_id=int(div_raw))
    return list(
        qs.exclude(job_position='')
        .values_list('job_position', flat=True)
        .distinct()
        .order_by('job_position'),
    )


def user_display_label(user: User) -> str:
    profile = getattr(user, 'profile', None)
    full_name = profile.full_name if profile and profile.full_name else user.get_full_name() or user.username
    code = profile.employee_code if profile and profile.employee_code else '—'
    return f'{full_name} · {code} · {user.username}'
