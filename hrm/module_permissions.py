"""
Phân quyền menu theo Phòng ban — JustPlay Portal.

Mỗi phòng ban có danh sách module được phép truy cập.
Thành viên thuộc phòng ban chỉ thấy menu và URL tương ứng.
"""

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages

from hrm.permissions import get_profile

MODULE_ANNOUNCEMENTS = 'announcements'
MODULE_RECRUITMENT = 'recruitment'
MODULE_TRAINING = 'training'
MODULE_ASSESSMENT = 'assessment'
MODULE_HRM = 'hrm'
MODULE_KPI = 'kpi'
MODULE_REPORTS = 'reports'
MODULE_GUIDE = 'guide'
MODULE_DOCUMENTS = 'documents'
MODULE_PERMISSIONS = 'permissions'

MODULE_CHOICES = [
    (MODULE_ANNOUNCEMENTS, 'Thông báo'),
    (MODULE_RECRUITMENT, 'Tuyển dụng'),
    (MODULE_TRAINING, 'Đào tạo'),
    (MODULE_ASSESSMENT, 'Kiểm tra'),
    (MODULE_HRM, 'Nhân sự'),
    (MODULE_KPI, 'Hiệu suất (KPI)'),
    (MODULE_REPORTS, 'Báo cáo'),
    (MODULE_GUIDE, 'Hướng dẫn'),
    (MODULE_DOCUMENTS, 'Tài liệu'),
    (MODULE_PERMISSIONS, 'Phân quyền'),
]

ALL_MODULE_KEYS = {key for key, _ in MODULE_CHOICES}

MODULE_LABELS = dict(MODULE_CHOICES)

# Đường dẫn luôn cho phép (không thuộc module menu)
EXEMPT_PATH_PREFIXES = (
    '/accounts/',
    '/change-password',
    '/admin-panel/',
    '/static/',
    '/media/',
    '/login-redirect/',
)

# Map prefix URL → module (thứ tự quan trọng — dài/specific trước)
PATH_MODULE_RULES = [
    ('/dashboard/users/', MODULE_HRM),
    ('/dashboard/org/', MODULE_HRM),
    ('/dashboard/departments/', MODULE_HRM),
    ('/dashboard/divisions/', MODULE_HRM),
    ('/dashboard/exam/', MODULE_ASSESSMENT),
    ('/dashboard/results/', MODULE_ASSESSMENT),
    ('/dashboard/competency/', MODULE_ASSESSMENT),
    ('/announcements/', MODULE_ANNOUNCEMENTS),
    ('/hr/', MODULE_RECRUITMENT),
    ('/training/', MODULE_TRAINING),
    ('/exams/', MODULE_ASSESSMENT),
    ('/kpi/', MODULE_KPI),
    ('/reports/', MODULE_REPORTS),
    ('/huong-dan/', MODULE_GUIDE),
    ('/tai-lieu/', MODULE_DOCUMENTS),
]

DASHBOARD_TAB_MODULES = {
    'recruitment': MODULE_RECRUITMENT,
    'training': MODULE_TRAINING,
    'assessment': MODULE_ASSESSMENT,
}


def bypass_department_modules(user) -> bool:
    """Tài khoản hệ thống — không bị giới hạn theo phòng ban."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return user.is_superuser or user.username == 'admin'


def get_user_department(user):
    profile = get_profile(user)
    if not profile:
        return None
    return profile.department


def get_department_enabled_modules(department) -> set:
    """Module được phép của phòng ban. Chưa cấu hình = full quyền."""
    if department is None:
        return set(ALL_MODULE_KEYS)

    from hrm.models import DepartmentMenuPermission

    try:
        perm = department.menu_permissions
    except DepartmentMenuPermission.DoesNotExist:
        return set(ALL_MODULE_KEYS)

    enabled = {m for m in (perm.modules or []) if m in ALL_MODULE_KEYS}
    if not enabled:
        return set(ALL_MODULE_KEYS)
    return enabled


def get_user_enabled_modules(user) -> set:
    if bypass_department_modules(user):
        return set(ALL_MODULE_KEYS)
    department = get_user_department(user)
    return get_department_enabled_modules(department)


def user_can_access_module(user, module_key: str) -> bool:
    """Phòng ban + vai trò — quyền xem module."""
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.role_permissions import role_allows_view
    return role_allows_view(user, module_key)


def user_can_edit_module(user, module_key: str) -> bool:
    """Phòng ban + vai trò — quyền cập nhật module."""
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.role_permissions import role_allows_edit
    return role_allows_edit(user, module_key)


def user_can_view_module(user, module_key: str) -> bool:
    """Alias — quyền xem module (phòng ban + vai trò)."""
    return user_can_access_module(user, module_key)


def resolve_module_from_request(path: str, tab: str | None = None) -> str | None:
    """Xác định module từ URL. None = không thuộc module menu."""
    if path in ('', '/'):
        return None

    for prefix in EXEMPT_PATH_PREFIXES:
        if path.startswith(prefix):
            return None

    if path.startswith('/dashboard/permissions'):
        return MODULE_PERMISSIONS

    if '/departments/' in path and path.rstrip('/').endswith('/permissions'):
        return MODULE_PERMISSIONS

    for prefix, module_key in PATH_MODULE_RULES:
        if path.startswith(prefix):
            return module_key

    if path.rstrip('/') == '/dashboard' or path == '/dashboard/':
        if tab and tab in DASHBOARD_TAB_MODULES:
            return DASHBOARD_TAB_MODULES[tab]
        return None

    return None


def department_access_denied_message(module_key: str) -> str:
    label = MODULE_LABELS.get(module_key, module_key)
    return (
        f'Phòng ban của bạn không được phép truy cập chức năng "{label}". '
        'Liên hệ HR hoặc IT nếu cần quyền.'
    )


def handle_department_access_denied(request, module_key: str):
    message = department_access_denied_message(module_key)
    accept = request.headers.get('Accept', '')
    if (
        'application/json' in accept
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('X-CSRFToken')
    ):
        return JsonResponse({'status': 'error', 'message': message}, status=403)

    messages.error(request, message)
    return redirect('home_portal')


def can_manage_permissions(user) -> bool:
    """Quyền cập nhật cấu hình phân quyền (phòng ban + vai trò)."""
    if bypass_department_modules(user):
        return True
    return user_can_edit_module(user, MODULE_PERMISSIONS)


def can_manage_department_permissions(user) -> bool:
    """Alias tương thích."""
    return can_manage_permissions(user)
