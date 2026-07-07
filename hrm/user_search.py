"""Tìm kiếm danh sách nhân sự — server-side, qua mọi trang phân trang."""

from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.db.models import F, IntegerField, Q
from django.db.models.expressions import RawSQL

from hrm.models import Profile

from PortalJustPlay.list_search import apply_user_search
from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
)

# Tài khoản quản trị hệ thống — không hiển thị trên danh sách nhân sự
HIDDEN_HRM_LIST_USERNAMES = ('admin',)
_PROTECTED_USERNAMES = {name.lower() for name in HIDDEN_HRM_LIST_USERNAMES}


def is_protected_system_user(user) -> bool:
    """Tài khoản hệ thống — không xóa / không đổi trạng thái qua UI nhân sự."""
    username = (getattr(user, 'username', None) or '').strip().lower()
    return username in _PROTECTED_USERNAMES


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
    'birth_date': 'profile__date_of_birth',
    'probation': 'profile__on_probation',
    'gender': 'profile__gender',
    'permission_group': 'profile__permission_group__name',
    'role': 'profile__role',
    'last_login': 'last_login',
}

USER_LIST_TABLE_COLUMNS = (
    {'key': 'code', 'label': 'Mã NS', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-code', 'sortable': True, 'default': True, 'required': True},
    {'key': 'name', 'label': 'Họ và tên', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-name', 'sortable': True, 'default': True, 'required': True},
    {'key': 'account', 'label': 'Tài khoản', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-account', 'sortable': True, 'default': True},
    {'key': 'department', 'label': 'Phòng ban', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-dept', 'sortable': True, 'default': True},
    {'key': 'division', 'label': 'Bộ phận', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-division', 'sortable': True, 'default': True},
    {'key': 'position', 'label': 'Vị trí', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-position', 'sortable': True, 'default': True},
    {'key': 'job_title', 'label': 'Chức vụ', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-job-title', 'sortable': True, 'default': True},
    {'key': 'birth_date', 'label': 'Ngày sinh', 'th_tone': 'cap', 'th_align': 'center', 'col_class': 'jp-hrm-col-date', 'sortable': True, 'default': True},
    {'key': 'probation', 'label': 'Thử việc', 'th_tone': 'cap', 'th_align': 'center', 'col_class': 'jp-hrm-col-probation', 'sortable': True, 'default': True},
    {'key': 'gender', 'label': 'Giới tính', 'th_tone': 'cap', 'th_align': 'center', 'col_class': 'jp-hrm-col-gender', 'sortable': True, 'default': True},
    {'key': 'permission_group', 'label': 'Nhóm quyền', 'th_tone': 'cap', 'th_align': 'start', 'col_class': 'jp-hrm-col-perm-group', 'sortable': True, 'default': False},
    {'key': 'role', 'label': 'Vai trò HT', 'th_tone': 'cap', 'th_align': 'center', 'col_class': 'jp-hrm-col-role', 'sortable': True, 'default': False},
    {'key': 'last_login', 'label': 'Đăng nhập cuối', 'th_tone': 'cap', 'th_align': 'center', 'col_class': 'jp-hrm-col-last-login', 'sortable': True, 'default': False},
    {'key': None, 'label': 'Thao tác', 'th_tone': 'cap', 'th_align': 'end', 'col_class': 'jp-hrm-col-actions', 'sortable': False, 'default': True, 'required': True},
)


def _user_list_th_class(spec: dict) -> str:
    parts = [
        'jp-hrm-list-th',
        f"jp-hrm-list-th--{spec.get('th_tone', 'cap')}",
        f"jp-hrm-list-th--{spec.get('th_align', 'start')}",
    ]
    col_class = spec.get('col_class')
    if col_class:
        parts.append(f'{col_class}-h')
    if col_class == 'jp-hrm-col-code':
        parts.append('ps-md-4')
    if col_class == 'jp-hrm-col-actions':
        parts.append('pe-md-4')
    return ' '.join(parts)

EMPLOYMENT_STATUS_LABELS = {
    '': 'Tất cả',
    'active': 'Đang làm',
    'inactive': 'Nghỉ làm',
}
EMPLOYMENT_STATUS_DEFAULT = 'active'


def resolve_employment_status_from_request(request) -> str:
    """Mặc định «Đang làm» khi URL không có ?status=; «Tất cả» khi ?status= rỗng."""
    if 'status' not in request.GET:
        return EMPLOYMENT_STATUS_DEFAULT
    raw = (request.GET.get('status') or '').strip().lower()
    if raw not in EMPLOYMENT_STATUS_LABELS:
        return EMPLOYMENT_STATUS_DEFAULT
    return raw


def filter_users_by_employment_status(queryset, status: str | None):
    """Lọc theo trạng thái làm việc: active / inactive."""
    raw = (status or '').strip().lower()
    if raw == 'active':
        return queryset.filter(profile__is_employed=True)
    if raw == 'inactive':
        return queryset.filter(profile__is_employed=False)
    return queryset


PROBATION_FILTER_LABELS = {
    '': 'Tất cả',
    'yes': 'Đang TV',
    'no': 'Không TV',
}


def resolve_probation_filter_from_request(request) -> str:
    if 'probation' not in request.GET:
        return ''
    raw = (request.GET.get('probation') or '').strip().lower()
    if raw not in PROBATION_FILTER_LABELS:
        return ''
    return raw


def filter_users_by_probation(queryset, probation: str | None):
    raw = (probation or '').strip().lower()
    if raw == 'yes':
        return queryset.filter(profile__on_probation=True)
    if raw == 'no':
        return queryset.filter(profile__on_probation=False)
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


def _employee_code_sort_sql() -> str:
    user_table = User._meta.db_table
    profile_table = Profile._meta.db_table
    return f"""
        (SELECT CASE
            WHEN p.employee_code IS NULL OR BTRIM(p.employee_code) = '' THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(p.employee_code, '[^0-9]', '', 'g'), '')::INTEGER
        END
        FROM {profile_table} p
        WHERE p.user_id = {user_table}.id)
    """


def apply_user_list_sort(queryset, sort_key: str, sort_dir: str):
    """Sắp xếp queryset danh sách NV; mã NS sort theo phần số (001 < 11 < 55 < 101)."""
    if sort_key == 'code':
        queryset = queryset.annotate(
            _code_sort_num=RawSQL(
                _employee_code_sort_sql(),
                [],
                output_field=IntegerField(),
            ),
        )
        code_text_order = 'profile__employee_code' if sort_dir == 'asc' else '-profile__employee_code'
        if sort_dir == 'asc':
            return queryset.order_by(
                F('_code_sort_num').asc(nulls_last=True),
                code_text_order,
                'username',
            )
        return queryset.order_by(
            F('_code_sort_num').desc(nulls_first=True),
            code_text_order,
            'username',
        )

    _, _, order_fields = resolve_user_list_sort(sort_key, sort_dir)
    return queryset.order_by(*order_fields)


def user_list_query_params(request, **overrides) -> dict[str, str]:
    keys = ('department', 'division', 'position', 'permission_group', 'q', 'status', 'probation', 'sort', 'dir', 'page')
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


def user_list_nav_query_string(request, page_number: int | None = None) -> str:
    """Query giữ bộ lọc + trang — dùng khi mở/sau form sửa NV."""
    params = user_list_query_params(request)
    if page_number is not None and page_number > 1:
        params['page'] = str(page_number)
    else:
        page_raw = (request.GET.get('page') or '').strip()
        if page_raw.isdigit() and int(page_raw) > 1:
            params['page'] = page_raw
    return urlencode(params)


def user_list_url(request, page_number: int | None = None) -> str:
    from django.urls import reverse

    qs = user_list_nav_query_string(request, page_number=page_number)
    base = reverse('user_list')
    return f'{base}?{qs}' if qs else base


def redirect_user_list_preserve_filters(request, *, from_post: bool = False):
    """Redirect danh sách NV — giữ nguyên bộ lọc (và trang) từ GET hoặc hidden POST."""
    from django.shortcuts import redirect
    from django.urls import reverse

    if from_post:
        qs = (request.POST.get('list_return_query') or '').strip()
    else:
        qs = user_list_nav_query_string(request)
    url = reverse('user_list')
    return redirect(f'{url}?{qs}' if qs else url)


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
        col['th_class'] = _user_list_th_class(spec)
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


def issue_recipient_org_name(profile) -> str:
    """Bộ phận (division) hoặc phòng ban nếu không có bộ phận."""
    if not profile:
        return ''
    if profile.division_id and profile.division:
        return profile.division.name
    if profile.department_id and profile.department:
        return profile.department.name
    return ''


def issue_recipient_label(user: User) -> str:
    """Nhãn người nhận phiếu xuất: Tên - Bộ phận."""
    profile = getattr(user, 'profile', None)
    full_name = profile.full_name if profile and profile.full_name else user.get_full_name() or user.username
    org = issue_recipient_org_name(profile)
    if org:
        return f'{full_name} - {org}'
    return full_name


def search_issue_recipients(query: str, *, limit: int = 50) -> list[dict]:
    """Tìm NV đang làm việc cho TomSelect người nhận phiếu xuất."""
    qs = exclude_hidden_hrm_users(
        User.objects.filter(is_active=True, profile__is_employed=True),
    ).select_related('profile', 'profile__department', 'profile__division')
    if (query or '').strip():
        qs = filter_users_by_search(qs, query.strip())
    qs = qs.order_by('profile__full_name', 'username')[:limit]
    results = []
    for user in qs:
        profile = getattr(user, 'profile', None)
        full_name = profile.full_name if profile and profile.full_name else user.get_full_name() or user.username
        code = profile.employee_code if profile and profile.employee_code else ''
        division = profile.division.name if profile and profile.division_id else ''
        department = profile.department.name if profile and profile.department_id else ''
        results.append({
            'id': user.pk,
            'text': issue_recipient_label(user),
            'name': full_name,
            'code': code,
            'division': division,
            'department': department,
        })
    return results


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

    if role not in (ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR):
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
            if div_id:
                base = base.filter(profile__division_id=div_id)
            elif dept_id:
                base = base.filter(profile__department_id=dept_id)
        elif role == ROLE_DEPARTMENT_HEAD:
            base = base.filter(
                profile__role__in=[ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD],
            )
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


def subordinate_candidates_json(qs):
    """Serialize queryset ứng viên cấp dưới cho user_picker AJAX."""
    rows = []
    for user in qs:
        profile = getattr(user, 'profile', None)
        full_name = profile.full_name if profile and profile.full_name else user.username
        employee_code = profile.employee_code if profile and profile.employee_code else ''
        username = user.username
        job_position = profile.job_position if profile else ''
        role = profile.role if profile else ''
        role_display = profile.get_role_display() if profile else ''
        department_id = profile.department_id if profile else None
        division_id = profile.division_id if profile else None
        department_name = profile.department.name if profile and profile.department_id else ''
        division_name = profile.division.name if profile and profile.division_id else ''
        search_parts = [
            full_name,
            employee_code,
            username,
            job_position,
            role_display,
            department_name,
            division_name,
        ]
        rows.append({
            'id': user.pk,
            'full_name': full_name,
            'employee_code': employee_code,
            'username': username,
            'job_position': job_position,
            'role': role,
            'role_display': role_display,
            'department_id': department_id or '',
            'division_id': division_id or '',
            'department_name': department_name,
            'division_name': division_name,
            'label': user_display_label(user),
            'search': ' '.join(part for part in search_parts if part).lower(),
        })
    return rows


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
        if div_id:
            return 'Gợi ý: chọn NV hoặc Tổ trưởng cùng bộ phận.'
        if dept_id:
            return 'Gợi ý: chọn NV hoặc Tổ trưởng cùng phòng ban.'
        return 'Chọn phòng ban / bộ phận bên trái để thu hẹp danh sách.'
    if role == ROLE_DEPARTMENT_HEAD:
        if dept_id:
            return 'Gợi ý: chọn NV / Tổ trưởng / Trưởng bộ phận cùng phòng ban.'
        return 'Chọn phòng ban bên trái để thu hẹp danh sách.'
    if role == ROLE_DIRECTOR:
        return 'Gợi ý: chọn nhân viên / tổ trưởng / trưởng bộ phận trong công ty.'
    return ''
