"""Tìm kiếm danh sách nhân sự — server-side, qua mọi trang phân trang."""

from django.contrib.auth.models import User
from django.db.models import Q

from PortalJustPlay.list_search import apply_user_search
from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
)

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


def job_positions_cascade_for_filter() -> dict[str, list[str]]:
    """Map scope → vị trí (dropdown lọc NV — cập nhật client khi đổi phòng/bộ phận)."""
    from hrm.models import Department
    from hrm.org_structure import divisions_for_user_list_filter

    result: dict[str, list[str]] = {
        '': distinct_job_positions_for_filter(),
        'none': distinct_job_positions_for_filter(department_id='none'),
    }
    for dept in Department.objects.filter(is_active=True).order_by('sort_order', 'name'):
        dept_key = str(dept.pk)
        result[dept_key] = distinct_job_positions_for_filter(department_id=dept_key)
        for div in divisions_for_user_list_filter(dept.pk):
            scope = f'{dept_key}:{div.pk}'
            result[scope] = distinct_job_positions_for_filter(
                department_id=dept_key,
                division_id=str(div.pk),
            )
    return result


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


def _pk_or_none(value) -> int | None:
    if value is None or value == '':
        return None
    if isinstance(value, int):
        return value
    raw = str(value).strip()
    return int(raw) if raw.isdigit() else None


def subordinate_candidate_queryset(
    *,
    exclude_user_id: int | None = None,
    manager_role: str | None = None,
    department_id=None,
    division_id=None,
    extra_user_ids: list[int] | None = None,
):
    """
    Danh sách NV có thể gán làm cấp dưới trực tiếp theo vai trò quản lý.
    Luôn gồm extra_user_ids (đã chọn trước đó) để không mất khi đổi phòng ban.
    """
    role = (manager_role or '').strip()
    dept_id = _pk_or_none(department_id)
    div_id = _pk_or_none(division_id)

    if role not in (ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
        base = User.objects.none()
    else:
        base = exclude_hidden_hrm_users(
            User.objects.filter(is_active=True, profile__is_employed=True),
        ).exclude(profile__role=ROLE_DIRECTOR)

        if exclude_user_id:
            base = base.exclude(pk=exclude_user_id)

        if role == ROLE_TEAM_LEADER:
            base = base.filter(profile__role=ROLE_EMPLOYEE)
            if div_id:
                base = base.filter(profile__division_id=div_id)
            elif dept_id:
                base = base.filter(profile__department_id=dept_id)
        elif role == ROLE_DIVISION_HEAD:
            base = base.filter(profile__role__in=[ROLE_EMPLOYEE, ROLE_TEAM_LEADER])
            if dept_id:
                base = base.filter(profile__department_id=dept_id)
        # ROLE_DIRECTOR: toàn công ty (trừ giám đốc khác)

        base = base.select_related('profile', 'profile__department', 'profile__division')

    extra_ids = [int(x) for x in (extra_user_ids or []) if str(x).isdigit()]
    if extra_ids:
        qs = User.objects.filter(
            Q(pk__in=base.values('pk')) | Q(pk__in=extra_ids),
        ).select_related('profile', 'profile__department', 'profile__division')
    else:
        qs = base

    return exclude_hidden_hrm_users(qs).order_by('profile__full_name', 'username')


def subordinate_scope_hint(
    *,
    manager_role: str | None = None,
    department_id=None,
    division_id=None,
) -> str:
    role = (manager_role or '').strip()
    dept_id = _pk_or_none(department_id)
    div_id = _pk_or_none(division_id)

    if role == ROLE_TEAM_LEADER:
        if div_id:
            return 'Gợi ý: chọn nhân viên cùng bộ phận (vai trò Nhân viên).'
        if dept_id:
            return 'Gợi ý: chọn nhân viên cùng phòng ban khi chưa gán bộ phận.'
        return 'Chọn phòng ban / bộ phận bên trái để thu hẹp danh sách.'
    if role == ROLE_DIVISION_HEAD:
        if dept_id:
            return 'Gợi ý: chọn NV hoặc Tổ trưởng cùng phòng ban.'
        return 'Chọn phòng ban bên trái để thu hẹp danh sách.'
    if role == ROLE_DIRECTOR:
        return 'Gợi ý: chọn nhân viên / tổ trưởng / trưởng bộ phận trong công ty.'
    return ''
