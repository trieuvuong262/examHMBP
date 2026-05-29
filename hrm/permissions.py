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


def _has_reports_module_access(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import MODULE_REPORTS
    from hrm.role_permissions import user_can_view_module
    return user_can_view_module(user, MODULE_REPORTS)


def get_report_team_users(viewer):
    """Nhân viên cấp dưới trực tiếp — cấu hình tại Nhân sự → Sửa NV → Nhân viên dưới quyền."""
    if not getattr(viewer, 'is_authenticated', False):
        return User.objects.none()

    profile = get_profile(viewer)
    if not profile:
        return User.objects.none()

    return profile.subordinates.filter(
        is_active=True,
        profile__is_employed=True,
    ).select_related('profile').order_by('profile__full_name', 'username')


def has_report_subordinates(user) -> bool:
    return get_report_team_users(user).exists()


def can_view_team_reports(user) -> bool:
    """Xem báo cáo của nhân viên cấp dưới trực tiếp (đã cấu hình trong Nhân sự)."""
    return _has_reports_module_access(user) and has_report_subordinates(user)


def can_submit_daily_report(user) -> bool:
    """Nộp báo cáo cá nhân — Giám đốc chỉ xem, không nộp."""
    if not _has_reports_module_access(user):
        return False
    return not is_director(user)


def can_view_user_report(viewer, report) -> bool:
    if not getattr(viewer, 'is_authenticated', False):
        return False
    if report.employee_id == viewer.id:
        return can_submit_daily_report(viewer)
    return get_report_team_users(viewer).filter(pk=report.employee_id).exists()


def can_review_user_report(viewer, report) -> bool:
    """Duyệt / phản hồi báo cáo cấp dưới trực tiếp."""
    if report.employee_id == viewer.id:
        return False
    return get_report_team_users(viewer).filter(pk=report.employee_id).exists()


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


def _has_tasks_module_access(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import MODULE_TASKS
    from hrm.role_permissions import user_can_view_module
    return user_can_view_module(user, MODULE_TASKS)


def get_task_assignable_users(assigner):
    """Nhân viên có thể được giao việc — cùng danh sách cấp dưới trực tiếp."""
    return get_report_team_users(assigner)


def has_task_subordinates(user) -> bool:
    return get_task_assignable_users(user).exists()


def can_assign_tasks(user) -> bool:
    """Giao việc — cần quyền cập nhật module Công việc và có cấp dưới trực tiếp (kể cả Giám đốc)."""
    if not _has_tasks_module_access(user):
        return False
    from hrm.module_permissions import MODULE_TASKS
    from hrm.role_permissions import user_can_edit_module
    return user_can_edit_module(user, MODULE_TASKS) and has_task_subordinates(user)


def can_view_task(user, task) -> bool:
    if not _has_tasks_module_access(user):
        return False
    if task.assignee_id == user.id or task.assigner_id == user.id:
        return True
    return False


def can_manage_assigned_task(user, task) -> bool:
    """Người giao việc — duyệt, hủy, giao lại."""
    if not _has_tasks_module_access(user):
        return False
    return task.assigner_id == user.id
