"""
Phân quyền thống nhất — JustPlay Portal.

Vai trò (Profile.role):
  EMPLOYEE — nhân viên xưởng
  HOD      — tổ trưởng / trưởng BP (báo cáo team, chấm KPI cấp dưới)
  GM       — giám đốc (KPI toàn công ty, thường có is_staff)

Quản trị portal (menu Tuyển dụng, Đào tạo, Kiểm tra, Nhân sự):
  is_staff — HR / IT / GM (GM được gán is_staff khi lưu Profile)
"""

from django.contrib.auth.models import User

ROLE_EMPLOYEE = 'EMPLOYEE'
ROLE_HOD = 'HOD'
ROLE_GM = 'GM'

MANAGER_ROLES = {ROLE_HOD, ROLE_GM}


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


def is_hod(user) -> bool:
    return user_role(user) == ROLE_HOD


def is_gm(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    return user_role(user) == ROLE_GM or user.is_superuser


def is_manager(user) -> bool:
    """HOD hoặc GM — quyền quản lý team (báo cáo, KPI)."""
    return user_role(user) in MANAGER_ROLES or is_gm(user)


def is_portal_admin(user) -> bool:
    """HR / quản trị portal — menu admin & @admin_only views."""
    return bool(getattr(user, 'is_authenticated', False) and user.is_staff)


def can_view_team_reports(user) -> bool:
    """Xem trang báo cáo team."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if is_portal_admin(user):
        return True
    return is_manager(user)


def get_report_team_users(viewer):
    """Danh sách nhân viên mà viewer được theo dõi báo cáo."""
    if not getattr(viewer, 'is_authenticated', False):
        return User.objects.none()

    profile = get_profile(viewer)
    if is_portal_admin(viewer) or is_gm(viewer):
        return User.objects.filter(is_active=True).select_related('profile').order_by(
            'profile__full_name', 'username',
        )
    if profile and profile.role == ROLE_HOD:
        return profile.subordinates.filter(is_active=True).select_related('profile').order_by(
            'profile__full_name', 'username',
        )
    return User.objects.none()


def can_manage_kpi_for_others(user) -> bool:
    """Giao KPI mới / import Excel."""
    return is_manager(user) or is_portal_admin(user)


def can_edit_user_guide(user) -> bool:
    """Chỉnh sửa trang hướng dẫn — quản lý (HOD/GM) hoặc HR/quản trị portal."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return is_manager(user) or is_portal_admin(user)


def portal_admin_denied_message() -> str:
    return (
        'Chức năng dành cho Phòng Nhân sự / Quản trị hệ thống. '
        'Liên hệ HR hoặc IT nếu bạn cần quyền truy cập.'
    )
