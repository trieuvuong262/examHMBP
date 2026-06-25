"""
Phân quyền menu theo Phòng ban — JustPlay Portal.

Mỗi phòng ban có danh sách module được phép truy cập.
Thành viên thuộc phòng ban chỉ thấy menu và URL tương ứng.
"""

import re

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
MODULE_AUDIT = 'audit'
MODULE_TASKS = 'tasks'
MODULE_DE_XUAT = 'de_xuat'
MODULE_HO_TRO = 'ho_tro'
MODULE_NAS_STORAGE = 'nas_storage'
MODULE_EQUIPMENT = 'equipment'
MODULE_FEEDBACK = 'feedback'
MODULE_UTILITIES = 'utilities'
MODULE_KIOTVIET = 'kiotviet'
MODULE_KHO_NPL = 'kho_npl'
MODULE_ODOO = 'odoo'

# Tạm ẩn khỏi sidebar + màn hình phân quyền — gỡ khỏi set khi bật lại.
HIDDEN_PORTAL_MODULES = frozenset({
    MODULE_KPI,
    MODULE_RECRUITMENT,
})

_ALL_MODULE_CHOICES = [
    (MODULE_ANNOUNCEMENTS, 'Thông báo'),
    (MODULE_RECRUITMENT, 'Tuyển dụng'),
    (MODULE_TRAINING, 'Đào tạo'),
    (MODULE_ASSESSMENT, 'Kiểm tra'),
    (MODULE_HRM, 'Nhân sự'),
    (MODULE_KPI, 'Hiệu suất (KPI)'),
    (MODULE_REPORTS, 'Báo cáo'),
    (MODULE_TASKS, 'Công việc'),
    (MODULE_DE_XUAT, 'Đề xuất mới'),
    (MODULE_HO_TRO, 'Hỗ trợ kỹ thuật'),
    (MODULE_EQUIPMENT, 'Quản lý thiết bị'),
    (MODULE_FEEDBACK, 'Góp ý'),
    (MODULE_UTILITIES, 'Tiện ích'),
    (MODULE_KIOTVIET, 'KiotViet'),
    (MODULE_ODOO, 'Odoo'),
    (MODULE_KHO_NPL, 'Kho Nguyên Phụ Liệu'),
    (MODULE_NAS_STORAGE, 'NAS'),
    (MODULE_DOCUMENTS, 'Tài liệu & Hỏi đáp'),
    (MODULE_GUIDE, 'Hướng dẫn'),
    (MODULE_PERMISSIONS, 'Phân quyền'),
    (MODULE_AUDIT, 'Quản trị hệ thống'),
]

MODULE_CHOICES = [
    (key, label) for key, label in _ALL_MODULE_CHOICES
    if key not in HIDDEN_PORTAL_MODULES
]

ALL_MODULE_KEYS = {key for key, _ in _ALL_MODULE_CHOICES}

MODULE_LABELS = dict(_ALL_MODULE_CHOICES)

# Nhãn phòng ban — khớp menu con sidebar (khác nhãn module trong ma trận).
DEPARTMENT_MODULE_LABELS = {
    MODULE_TRAINING: 'Bài học',
    MODULE_ASSESSMENT: 'Kiểm tra',
}

# Gộp hiển thị ma trận nhóm quyền — một nhóm «Đào tạo» như sidebar.
LEARNING_PERM_MATRIX_MODULES = frozenset({MODULE_TRAINING, MODULE_ASSESSMENT})
LEARNING_PERM_MATRIX_SUBMENUS = (
    (MODULE_TRAINING, 'lessons'),
    (MODULE_ASSESSMENT, 'exams'),
    (MODULE_TRAINING, 'manage'),
    (MODULE_ASSESSMENT, 'manage'),
)


def is_portal_module_visible(module_key: str) -> bool:
    return module_key not in HIDDEN_PORTAL_MODULES


def _visible_module_list(modules: list[str]) -> list[str]:
    return [key for key in modules if is_portal_module_visible(key)]


# Nhóm hiển thị form «Phân quyền menu» — khớp cấu trúc sidebar.
DEPARTMENT_MENU_SECTIONS = [
    {
        'label': 'Menu chính',
        'modules': _visible_module_list([
            MODULE_ANNOUNCEMENTS,
            MODULE_RECRUITMENT,
            MODULE_HRM,
            MODULE_KPI,
            MODULE_REPORTS,
            MODULE_TASKS,
        ]),
    },
    {
        'label': 'Đào tạo',
        'modules': _visible_module_list([MODULE_TRAINING, MODULE_ASSESSMENT]),
    },
    {
        'label': 'Yêu cầu',
        'modules': _visible_module_list([MODULE_DE_XUAT, MODULE_HO_TRO]),
    },
    {
        'label': 'Vận hành',
        'modules': _visible_module_list([
            MODULE_EQUIPMENT,
            MODULE_FEEDBACK,
            MODULE_UTILITIES,
            MODULE_KIOTVIET,
            MODULE_ODOO,
            MODULE_KHO_NPL,
            MODULE_NAS_STORAGE,
        ]),
    },
    {
        'label': 'Thư viện',
        'modules': _visible_module_list([MODULE_DOCUMENTS, MODULE_GUIDE]),
    },
    {
        'label': 'Hệ thống',
        'modules': _visible_module_list([MODULE_PERMISSIONS, MODULE_AUDIT]),
    },
]

# Đường dẫn luôn cho phép (không thuộc module menu)
EXEMPT_PATH_PREFIXES = (
    '/accounts/',
    '/change-password',
    '/profile/avatar',
    '/admin-panel/',
    '/static/',
    '/media/',
    '/login-redirect/',
    '/nhat-ky/rustdesk/api/dang-ky/',
    '/thiet-bi/api/quyet-cau-hinh/',
    # Web push portal — view tự kiểm tra user_portal_push_eligible (không cần module Tiện ích)
    '/tien-ich/push/',
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
    ('/nhat-ky/', MODULE_AUDIT),
    ('/cong-viec/', MODULE_TASKS),
    ('/yeu-cau/danh-muc-dinh-ky/', MODULE_DE_XUAT),
    ('/yeu-cau/cho-xu-ly/', MODULE_DE_XUAT),
    ('/yeu-cau/tao/', MODULE_DE_XUAT),
    ('/yeu-cau/cua-toi/', MODULE_DE_XUAT),
    ('/yeu-cau/sua-it/', MODULE_HO_TRO),
    ('/yeu-cau/de-xuat/', MODULE_DE_XUAT),
    ('/yeu-cau/ho-tro/', MODULE_HO_TRO),
    ('/thu-muc-nas/', MODULE_NAS_STORAGE),
    ('/thiet-bi/', MODULE_EQUIPMENT),
    ('/gop-y/', MODULE_FEEDBACK),
    ('/tien-ich/', MODULE_UTILITIES),
    ('/kiotviet/', MODULE_KIOTVIET),
    ('/odoo/', MODULE_ODOO),
    ('/kho-npl/', MODULE_KHO_NPL),
]

EQUIPMENT_PUBLIC_PREFIXES = (
    '/thiet-bi/qr/',
)

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
    if 'service_requests' in (perm.modules or []):
        enabled.add(MODULE_DE_XUAT)
        enabled.add(MODULE_HO_TRO)
    if not enabled:
        return set(ALL_MODULE_KEYS)
    return enabled


def get_user_enabled_modules(user) -> set:
    if bypass_department_modules(user):
        return set(ALL_MODULE_KEYS)
    department = get_user_department(user)
    return get_department_enabled_modules(department)


def user_can_access_module(user, module_key: str) -> bool:
    """Phòng ban + nhóm quyền — quyền xem module (hoặc bất kỳ menu con nào)."""
    if not is_portal_module_visible(module_key):
        return False
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.menu_permissions import user_can_access_any_menu
    from hrm.submenu_registry import module_has_submenus
    if module_has_submenus(module_key):
        return user_can_access_any_menu(user, module_key)
    from hrm.role_permissions import role_allows_view
    return role_allows_view(user, module_key)


def user_can_edit_module(user, module_key: str) -> bool:
    """Phòng ban + nhóm quyền — thêm/sửa/xóa module."""
    if not is_portal_module_visible(module_key):
        return False
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.role_permissions import role_allows_edit
    return role_allows_edit(user, module_key)


def user_can_create_module(user, module_key: str) -> bool:
    if not is_portal_module_visible(module_key):
        return False
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.group_permissions import PERM_CREATE, get_user_module_perm
    return bool(get_user_module_perm(user, module_key).get(PERM_CREATE))


def user_can_update_module(user, module_key: str) -> bool:
    if not is_portal_module_visible(module_key):
        return False
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.group_permissions import PERM_UPDATE, get_user_module_perm
    return bool(get_user_module_perm(user, module_key).get(PERM_UPDATE))


def user_can_delete_module(user, module_key: str) -> bool:
    if not is_portal_module_visible(module_key):
        return False
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.group_permissions import PERM_DELETE, get_user_module_perm
    return bool(get_user_module_perm(user, module_key).get(PERM_DELETE))


def user_can_export_module(user, module_key: str) -> bool:
    if not is_portal_module_visible(module_key):
        return False
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    from hrm.group_permissions import PERM_EXPORT, get_user_module_perm
    return bool(get_user_module_perm(user, module_key).get(PERM_EXPORT))


def user_can_view_module(user, module_key: str) -> bool:
    """Alias — quyền xem module (phòng ban + vai trò)."""
    return user_can_access_module(user, module_key)


def resolve_module_from_request(path: str, tab: str | None = None) -> str | None:
    """Xác định module từ URL. None = không thuộc module menu."""
    if path in ('', '/'):
        return None

    for prefix in EQUIPMENT_PUBLIC_PREFIXES:
        if path.startswith(prefix):
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

    legacy_detail = re.match(r'^/yeu-cau/(\d+)/$', path)
    if legacy_detail:
        pk = int(legacy_detail.group(1))
        try:
            from service_requests.models import RequestType, ServiceRequest
            code = ServiceRequest.objects.filter(pk=pk).values_list(
                'request_type__code', flat=True,
            ).first()
            if code == RequestType.CODE_IT_REPAIR:
                return MODULE_HO_TRO
            if code == RequestType.CODE_ASSET_PURCHASE:
                return MODULE_DE_XUAT
        except Exception:
            pass
        return None

    if path.startswith('/yeu-cau/'):
        return None

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
