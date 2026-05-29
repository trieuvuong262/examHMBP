"""
Phân quyền thống nhất — JustPlay Portal.

Vai trò (Profile.role):
  EMPLOYEE      — Nhân viên
  TEAM_LEADER   — Tổ trưởng
  DIVISION_HEAD — Trưởng bộ phận
  DIRECTOR      — Giám đốc (staff portal khi lưu Profile)

Quản trị portal (menu Tuyển dụng, Đào tạo, Kiểm tra, Nhân sự):
  is_staff — HR / IT / Giám đốc
"""

from django.contrib.auth.models import User

ROLE_EMPLOYEE = 'EMPLOYEE'
ROLE_TEAM_LEADER = 'TEAM_LEADER'
ROLE_DIVISION_HEAD = 'DIVISION_HEAD'
ROLE_DIRECTOR = 'DIRECTOR'

# Alias tương thích code cũ
ROLE_HOD = ROLE_TEAM_LEADER
ROLE_GM = ROLE_DIRECTOR

ROLE_CHOICES = [
    (ROLE_EMPLOYEE, 'Nhân viên'),
    (ROLE_TEAM_LEADER, 'Tổ trưởng'),
    (ROLE_DIVISION_HEAD, 'Trưởng bộ phận'),
    (ROLE_DIRECTOR, 'Giám đốc'),
]

MANAGER_ROLES = {ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR}
SUBORDINATE_MANAGER_ROLES = {ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD}


def get_profile(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    try:
        return user.profile
    except Exception:
        return None


def user_role(user) -> str:
    profile = get_profile(user)
    return profile.role if profile else ROLE_EMPLOYEE


def role_display(user) -> str:
    profile = get_profile(user)
    if not profile:
        return 'Nhân viên'
    return profile.get_role_display()


def is_team_leader(user) -> bool:
    return user_role(user) == ROLE_TEAM_LEADER


def is_division_head(user) -> bool:
    return user_role(user) == ROLE_DIVISION_HEAD


def is_director(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    return user_role(user) == ROLE_DIRECTOR or user.is_superuser


def is_hod(user) -> bool:
    """Tổ trưởng (alias tương thích)."""
    return is_team_leader(user)


def is_gm(user) -> bool:
    """Giám đốc (alias tương thích)."""
    return is_director(user)


def is_manager(user) -> bool:
    """Tổ trưởng, trưởng bộ phận hoặc giám đốc — quyền quản lý team."""
    return user_role(user) in MANAGER_ROLES or is_director(user)


def is_portal_admin(user) -> bool:
    """HR / quản trị portal — menu admin & @admin_only views."""
    return bool(getattr(user, 'is_authenticated', False) and user.is_staff)


def can_view_team_reports(user) -> bool:
    """Xem trang báo cáo team."""
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import MODULE_REPORTS
    from hrm.role_permissions import user_can_view_module
    return user_can_view_module(user, MODULE_REPORTS)


def get_report_team_users(viewer):
    """Danh sách nhân viên mà viewer được theo dõi báo cáo."""
    if not getattr(viewer, 'is_authenticated', False):
        return User.objects.none()

    profile = get_profile(viewer)
    if is_portal_admin(viewer) or is_director(viewer):
        return User.objects.filter(is_active=True).select_related('profile').order_by(
            'profile__full_name', 'username',
        )
    if profile and profile.role == ROLE_DIVISION_HEAD and profile.division_id:
        return User.objects.filter(
            is_active=True,
            profile__division_id=profile.division_id,
        ).select_related('profile').order_by('profile__full_name', 'username')
    if profile and profile.role in SUBORDINATE_MANAGER_ROLES:
        return profile.subordinates.filter(is_active=True).select_related('profile').order_by(
            'profile__full_name', 'username',
        )
    return User.objects.none()


def can_edit_user_guide(user) -> bool:
    """Chỉnh sửa trang hướng dẫn."""
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import MODULE_GUIDE, user_can_edit_module
    return user_can_edit_module(user, MODULE_GUIDE)


def can_manage_kpi_for_others(user) -> bool:
    """Giao KPI mới / import Excel."""
    from hrm.module_permissions import MODULE_KPI, user_can_edit_module
    return user_can_edit_module(user, MODULE_KPI)


def portal_admin_denied_message() -> str:
    return (
        'Chức năng dành cho Phòng Nhân sự / Quản trị hệ thống. '
        'Liên hệ HR hoặc IT nếu bạn cần quyền truy cập.'
    )
