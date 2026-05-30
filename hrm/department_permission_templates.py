"""
Mẫu nhóm quyền ban đầu (seed) — tham khảo, không ràng buộc phòng ban.

DEPARTMENT_PERMISSION_TEMPLATES chỉ dùng khi migrate / tạo mẫu lần đầu.
Quản trị viên tự sửa, xóa, thêm nhóm và gán cho từng nhân viên.
"""

from django.utils.text import slugify

from hrm.module_permissions import ALL_MODULE_KEYS
from hrm.permissions import ROLE_DIRECTOR, ROLE_DIVISION_HEAD

PROTECTED_GROUP_SLUG_PREFIX = 'mac-dinh-'
GROUP_LEVEL_LABELS = (
    ('nhan-vien', 'Nhân viên'),
    ('truong-phong', 'Trưởng phòng'),
)

M = {
    'announcements': 'announcements',
    'recruitment': 'recruitment',
    'training': 'training',
    'assessment': 'assessment',
    'hrm': 'hrm',
    'kpi': 'kpi',
    'reports': 'reports',
    'guide': 'guide',
    'documents': 'documents',
    'permissions': 'permissions',
    'audit': 'audit',
    'tasks': 'tasks',
    'service_requests': 'service_requests',
    'nas_storage': 'nas_storage',
}


def _f(view=False, create=False, update=False, delete=False, export=False) -> dict:
    if any((create, update, delete, export)):
        view = True
    return {
        'view': bool(view),
        'create': bool(create),
        'update': bool(update),
        'delete': bool(delete),
        'export': bool(export),
    }


NONE = _f()
VIEW = _f(view=True)
EDIT = _f(view=True, create=True, update=True, delete=True)
FULL = _f(view=True, create=True, update=True, delete=True, export=True)
MGR = _f(view=True, create=True, update=True, delete=False, export=True)


def _blank() -> dict:
    return {key: dict(NONE) for key in ALL_MODULE_KEYS}


def _build(*layers: dict) -> dict:
    result = _blank()
    for layer in layers:
        for key, perm in layer.items():
            if key in result and perm:
                result[key] = dict(perm)
    return result


def _portal_employee() -> dict:
    return _build({
        M['announcements']: VIEW,
        M['training']: VIEW,
        M['assessment']: VIEW,
        M['kpi']: VIEW,
        M['reports']: VIEW,
        M['guide']: VIEW,
        M['documents']: VIEW,
        M['tasks']: VIEW,
        M['service_requests']: _f(view=True, create=True),
        M['nas_storage']: VIEW,
    })


def _portal_manager() -> dict:
    return _build(
        _portal_employee(),
        {
            M['training']: MGR,
            M['assessment']: MGR,
            M['kpi']: MGR,
            M['reports']: MGR,
            M['guide']: MGR,
            M['tasks']: EDIT,
            M['service_requests']: MGR,
            M['documents']: MGR,
        },
    )


def _full_access() -> dict:
    return {key: dict(FULL) for key in ALL_MODULE_KEYS}


DEPARTMENT_PERMISSION_TEMPLATES = [
    {
        'code': 'tgd',
        'department_names': ('Tổng giám đốc', 'CÔNG TY TNHH JUST PLAY'),
        'employee_name': 'Tổng giám đốc — Nhân viên',
        'manager_name': 'Tổng giám đốc — Trưởng phòng',
        'employee': _build(
            _portal_employee(),
            {
                M['recruitment']: VIEW,
                M['hrm']: VIEW,
            },
        ),
        'manager': _full_access(),
    },
    {
        'code': 'dbcl',
        'department_names': ('ĐẢM BẢO CHẤT LƯỢNG',),
        'employee_name': 'ĐẢM BẢO CHẤT LƯỢNG — Nhân viên',
        'manager_name': 'ĐẢM BẢO CHẤT LƯỢNG — Trưởng phòng',
        'employee': _portal_employee(),
        'manager': _build(_portal_manager(), {M['assessment']: MGR}),
    },
    {
        'code': 'hcns',
        'department_names': ('HÀNH CHÍNH NHÂN SỰ',),
        'employee_name': 'HÀNH CHÍNH NHÂN SỰ — Nhân viên',
        'manager_name': 'HÀNH CHÍNH NHÂN SỰ — Trưởng phòng',
        'employee': _build(
            _portal_employee(),
            {
                M['hrm']: _f(view=True, create=True, update=True, export=True),
                M['recruitment']: _f(view=True, create=True, update=True, export=True),
            },
        ),
        'manager': _build(
            _portal_manager(),
            {
                M['hrm']: FULL,
                M['recruitment']: MGR,
                M['permissions']: VIEW,
            },
        ),
    },
    {
        'code': 'khsx',
        'department_names': ('KẾ HOẠCH SẢN XUẤT',),
        'employee_name': 'KẾ HOẠCH SẢN XUẤT — Nhân viên',
        'manager_name': 'KẾ HOẠCH SẢN XUẤT — Trưởng phòng',
        'employee': _portal_employee(),
        'manager': _portal_manager(),
    },
    {
        'code': 'kd-mkt',
        'department_names': ('KINH DOANH - MARKETING',),
        'employee_name': 'KINH DOANH - MARKETING — Nhân viên',
        'manager_name': 'KINH DOANH - MARKETING — Trưởng phòng',
        'employee': _build(_portal_employee(), {M['documents']: MGR}),
        'manager': _build(_portal_manager(), {M['documents']: MGR}),
    },
    {
        'code': 'rd',
        'department_names': ('R&D',),
        'employee_name': 'R&D — Nhân viên',
        'manager_name': 'R&D — Trưởng phòng',
        'employee': _build(_portal_employee(), {M['documents']: MGR}),
        'manager': _build(_portal_manager(), {M['documents']: EDIT}),
    },
    {
        'code': 'sx',
        'department_names': ('SẢN XUẤT',),
        'employee_name': 'SẢN XUẤT — Nhân viên',
        'manager_name': 'SẢN XUẤT — Trưởng phòng',
        'employee': _portal_employee(),
        'manager': _portal_manager(),
    },
    {
        'code': 'tckt',
        'department_names': ('TÀI CHÍNH KẾ TOÁN',),
        'employee_name': 'TÀI CHÍNH KẾ TOÁN — Nhân viên',
        'manager_name': 'TÀI CHÍNH KẾ TOÁN — Trưởng phòng',
        'employee': _portal_employee(),
        'manager': _build(_portal_manager(), {M['reports']: FULL}),
    },
    {
        'code': 'it',
        'department_names': ('IT',),
        'employee_name': 'IT — Nhân viên',
        'manager_name': 'IT — Trưởng phòng',
        'employee': _build(
            _portal_employee(),
            {
                M['guide']: MGR,
                M['permissions']: VIEW,
                M['audit']: VIEW,
            },
        ),
        'manager': _build(
            _portal_manager(),
            {
                M['guide']: FULL,
                M['permissions']: FULL,
                M['audit']: FULL,
            },
        ),
    },
]


def department_group_slug(code: str, level: str) -> str:
    return f'{code}-{level}'


def slugify_department_code(name: str) -> str:
    return slugify((name or '').strip()) or 'phong-ban'


def empty_permissions_matrix() -> dict:
    return _blank()


def group_slugs_for_department(department) -> list[str]:
    code = slugify_department_code(department.name)
    return [department_group_slug(code, level) for level, _ in GROUP_LEVEL_LABELS]


def is_protected_permission_group(slug: str) -> bool:
    return (slug or '').startswith(PROTECTED_GROUP_SLUG_PREFIX)


def department_name_to_code(dept_name: str) -> str | None:
    normalized = (dept_name or '').strip().casefold()
    if not normalized:
        return None
    for item in DEPARTMENT_PERMISSION_TEMPLATES:
        for name in item['department_names']:
            if name.casefold() == normalized:
                return item['code']
    return None


def default_group_slug_for_profile(department_name: str, role: str) -> str | None:
    """Legacy — migration 0024 gán mẫu lần đầu; runtime không dùng."""
    code = department_name_to_code(department_name)
    if not code:
        code = slugify_department_code(department_name)
    level = 'truong-phong' if role in {ROLE_DIRECTOR, ROLE_DIVISION_HEAD} else 'nhan-vien'
    return department_group_slug(code, level)


def permission_group_sort_key(name: str, slug: str) -> tuple:
    """Sắp xếp: phòng ban (theo thứ tự công ty) → NV trước TP → vai trò mặc định."""
    if is_protected_permission_group(slug):
        return (2, 0, name)
    if ' — ' in name:
        section, level = name.rsplit(' — ', 1)
        level_index = 0 if level.strip().casefold() == 'nhân viên' else 1
        dept_index = next(
            (i for i, t in enumerate(DEPARTMENT_PERMISSION_TEMPLATES)
             if section in t['department_names']
             or t['employee_name'].startswith(section + ' —')),
            -1,
        )
        if dept_index >= 0:
            return (0, dept_index, level_index, name)
        return (0, 500, section.casefold(), level_index, name)
    return (1, 0, name)
