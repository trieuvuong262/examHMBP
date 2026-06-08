"""Tìm kiếm danh sách nhân sự — server-side, qua mọi trang phân trang."""

from urllib.parse import urlencode

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


USER_LIST_SORT_COLUMNS = {
    'code': 'profile__employee_code',
    'name': 'profile__full_name',
    'account': 'username',
    'department': 'profile__department__name',
    'division': 'profile__division__name',
    'position': 'profile__job_position',
    'job_title': 'profile__job_title',
    'join_date': 'profile__join_date',
    'birth_date': 'profile__date_of_birth',
    'gender': 'profile__gender',
    'role': 'profile__role',
}

USER_LIST_TABLE_COLUMNS = (
    {'key': 'code', 'label': 'Mã NS', 'th_class': 'ps-4 py-3 text-muted', 'col_class': 'jp-hrm-col-code', 'sortable': True},
    {'key': 'name', 'label': 'Họ và tên', 'th_class': 'text-muted', 'col_class': 'jp-hrm-col-name', 'sortable': True},
    {'key': 'account', 'label': 'Account', 'th_class': 'text-muted', 'col_class': 'jp-hrm-col-account', 'sortable': True},
    {'key': 'department', 'label': 'Phòng ban', 'th_class': 'text-muted', 'col_class': 'jp-hrm-col-org', 'sortable': True},
    {'key': 'division', 'label': 'Bộ phận', 'th_class': 'text-muted', 'col_class': 'jp-hrm-col-org', 'sortable': True},
    {'key': 'position', 'label': 'Vị trí', 'th_class': 'text-muted', 'col_class': 'jp-hrm-col-org', 'sortable': True},
    {'key': 'job_title', 'label': 'Chức vụ', 'th_class': 'text-muted', 'col_class': 'jp-hrm-col-job-title', 'sortable': True},
    {'key': 'join_date', 'label': 'Ngày vào', 'th_class': 'text-muted jp-hrm-col-date', 'col_class': 'jp-hrm-col-date', 'sortable': True},
    {'key': 'birth_date', 'label': 'Ngày sinh', 'th_class': 'text-muted jp-hrm-col-date', 'col_class': 'jp-hrm-col-date', 'sortable': True},
    {'key': 'gender', 'label': 'Giới tính', 'th_class': 'text-muted text-center', 'col_class': 'jp-hrm-col-gender', 'sortable': True},
    {'key': 'role', 'label': 'Vai trò HT', 'th_class': 'text-muted text-center', 'col_class': 'jp-hrm-col-role', 'sortable': True},
    {'key': None, 'label': 'Thao tác', 'th_class': 'text-end pe-4 text-muted jp-hrm-col-actions-h', 'col_class': 'jp-hrm-col-actions', 'sortable': False},
)

EMPLOYMENT_STATUS_LABELS = {
    '': 'Tất cả trạng thái',
    'active': 'Đang làm',
    'inactive': 'Nghỉ làm',
}


def filter_users_by_employment_status(queryset, status: str | None):
    """Lọc theo trạng thái làm việc: active / inactive."""
    raw = (status or '').strip().lower()
    if raw == 'active':
        return queryset.filter(profile__is_employed=True)
    if raw == 'inactive':
        return queryset.filter(profile__is_employed=False)
    return queryset


def resolve_user_list_sort(sort_key: str | None, sort_dir: str | None) -> tuple[str, str, list[str]]:
    key = (sort_key or 'name').strip()
    if key not in USER_LIST_SORT_COLUMNS:
        key = 'name'
    direction = (sort_dir or 'asc').strip().lower()
    if direction not in ('asc', 'desc'):
        direction = 'asc'
    field = USER_LIST_SORT_COLUMNS[key]
    prefix = '-' if direction == 'desc' else ''
    return key, direction, [f'{prefix}{field}', 'username']


def user_list_query_params(request, **overrides) -> dict[str, str]:
    keys = ('department', 'division', 'position', 'q', 'status', 'sort', 'dir')
    data: dict[str, str] = {}
    for key in keys:
        if key in overrides:
            val = overrides[key]
        else:
            val = request.GET.get(key, '')
        if val is None:
            continue
        text = str(val).strip()
        if text:
            data[key] = text
    return data


def user_list_query_string(request, **overrides) -> str:
    return urlencode(user_list_query_params(request, **overrides))


def user_list_sort_href(request, column_key: str, current_sort: str, current_dir: str) -> str:
    if current_sort == column_key:
        next_dir = 'desc' if current_dir == 'asc' else 'asc'
    else:
        next_dir = 'asc'
    qs = user_list_query_string(request, sort=column_key, dir=next_dir)
    return f'?{qs}' if qs else '?'


def build_user_list_table_columns(request, sort_key: str, sort_dir: str) -> list[dict]:
    columns = []
    for spec in USER_LIST_TABLE_COLUMNS:
        col = dict(spec)
        key = col.get('key')
        if col.get('sortable') and key:
            col['sort_href'] = user_list_sort_href(request, key, sort_key, sort_dir)
            col['sort_active'] = sort_key == key
            col['sort_dir'] = sort_dir if col['sort_active'] else ''
        columns.append(col)
    return columns


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
