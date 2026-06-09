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
    """Trưởng bộ phận — Giám đốc có quyền tương đương (ẩn) trên mọi phòng ban."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return user_role(user) in {ROLE_DIVISION_HEAD, ROLE_DIRECTOR} or user.is_superuser


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


def format_team_user_label(user) -> str:
    """Nhãn chọn nhân viên: Họ tên · Mã NS · account."""
    profile = get_profile(user)
    full_name = profile.full_name if profile and profile.full_name else user.username
    code = profile.employee_code if profile and profile.employee_code else '—'
    return f'{full_name} · {code} · {user.username}'


def has_report_subordinates(user) -> bool:
    return get_report_team_users(user).exists()


def can_view_team_reports(user) -> bool:
    """Xem báo cáo của nhân viên cấp dưới trực tiếp (đã cấu hình trong Nhân sự)."""
    return _has_reports_module_access(user) and has_report_subordinates(user)


def can_submit_daily_report(user) -> bool:
    """Nộp báo cáo cá nhân — Giám đốc chỉ xem, không nộp."""
    if not _has_reports_module_access(user):
        return False
    from hrm.module_permissions import MODULE_REPORTS, user_can_create_module
    if not user_can_create_module(user, MODULE_REPORTS):
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
    if not get_report_team_users(viewer).filter(pk=report.employee_id).exists():
        return False
    from hrm.module_permissions import MODULE_REPORTS, user_can_update_module
    return user_can_update_module(viewer, MODULE_REPORTS)


def can_edit_user_guide(user) -> bool:
    """Chỉnh sửa trang hướng dẫn."""
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import MODULE_GUIDE, user_can_update_module
    return user_can_update_module(user, MODULE_GUIDE)


def can_manage_kpi_for_others(user) -> bool:
    """Giao KPI mới / import Excel."""
    from hrm.module_permissions import MODULE_KPI, user_can_create_module
    return user_can_create_module(user, MODULE_KPI)


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
    """
    Nhân viên có thể được giao việc:
    - Giám đốc: toàn bộ nhân viên đang làm việc (trừ giám đốc khác)
    - Trưởng bộ phận: toàn bộ nhân viên cùng phòng ban
    - Tổ trưởng: nhân viên cấp dưới trực tiếp (cấu hình Nhân sự)
    """
    profile = get_profile(assigner)
    if not profile:
        return User.objects.none()

    if profile.role == ROLE_DIRECTOR:
        return _all_company_task_users(exclude_pk=assigner.pk)

    if profile.role == ROLE_DIVISION_HEAD and profile.department_id:
        return _department_task_users(profile.department).exclude(pk=assigner.pk)

    return _filter_task_recipient_users(
        get_report_team_users(assigner),
        exclude_pk=assigner.pk,
    )


def _filter_task_recipient_users(qs, *, exclude_pk=None):
    """Lọc người có thể nhận việc — đang làm việc, có module Công việc, không phải giám đốc."""
    from hrm.module_permissions import MODULE_TASKS, user_can_access_module

    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    eligible_ids = [
        user.pk for user in qs.select_related('profile')
        if user_can_access_module(user, MODULE_TASKS)
        and can_receive_assigned_tasks(user)
    ]
    return User.objects.filter(pk__in=eligible_ids).select_related('profile').order_by(
        'profile__full_name', 'username',
    )


def _all_company_task_users(*, exclude_pk=None):
    """Toàn bộ nhân viên active — dùng khi giám đốc giao việc."""
    qs = User.objects.filter(
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile').order_by('profile__full_name', 'username')
    return _filter_task_recipient_users(qs, exclude_pk=exclude_pk)


def _department_task_users(department):
    """Nhân viên active trong phòng ban, có quyền module Công việc (trừ Giám đốc)."""
    if department is None:
        return User.objects.none()

    qs = User.objects.filter(
        profile__department=department,
        profile__is_employed=True,
        is_active=True,
    ).select_related('profile').order_by('profile__full_name', 'username')
    return _filter_task_recipient_users(qs)


def has_task_subordinates(user) -> bool:
    return get_task_assignable_users(user).exists()


def can_manage_team_tasks(user) -> bool:
    """
    Giao việc cá nhân & tạo dự án nội bộ — cần quyền sửa module Công việc.

    - Tổ trưởng: có cấp dưới trực tiếp (Nhân sự → Nhân viên dưới quyền)
    - Trưởng bộ phận: thuộc phòng ban (giao cho nhân sự cùng phòng)
    - Giám đốc: quyền sửa module Công việc
    """
    if not _has_tasks_module_access(user):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_create_module
    if not user_can_create_module(user, MODULE_TASKS):
        return False

    role = user_role(user)
    profile = get_profile(user)
    if role == ROLE_TEAM_LEADER:
        return has_task_subordinates(user)
    if role == ROLE_DIVISION_HEAD:
        return bool(profile and profile.department_id)
    if role == ROLE_DIRECTOR:
        return True
    return False


def can_assign_tasks(user) -> bool:
    return can_manage_team_tasks(user)


def can_create_internal_project(user) -> bool:
    return can_manage_team_tasks(user)


def can_receive_assigned_tasks(user) -> bool:
    """Nhận và thực hiện việc được giao — Giám đốc chỉ giao/duyệt, không nhận việc (giống báo cáo)."""
    if not _has_tasks_module_access(user):
        return False
    return not is_director(user)


CROSS_DEPT_CREATOR_ROLES = {ROLE_DIRECTOR, ROLE_DIVISION_HEAD}


def can_create_cross_dept_project(user) -> bool:
    """Chỉ Giám đốc hoặc Trưởng bộ phận — cần quyền sửa module Công việc."""
    if not _has_tasks_module_access(user):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_create_module
    if not user_can_create_module(user, MODULE_TASKS):
        return False
    return user_role(user) in CROSS_DEPT_CREATOR_ROLES


def can_create_any_project(user) -> bool:
    """Tạo dự án nội bộ hoặc liên phòng ban."""
    return can_create_internal_project(user) or can_create_cross_dept_project(user)


def is_cross_dept_dept_head_viewer(user, project) -> bool:
    """Trưởng bộ phận xem dự án liên phòng ban — Giám đốc xem tất cả."""
    if not project.is_cross_department:
        return False
    if is_director(user):
        return True
    profile = get_profile(user)
    if not profile or user_role(user) != ROLE_DIVISION_HEAD:
        return False
    if not profile.department_id:
        return False
    return project.departments.filter(pk=profile.department_id).exists()


def is_cross_dept_read_only_viewer(user, project) -> bool:
    return is_cross_dept_dept_head_viewer(user, project) and not can_manage_project(user, project)


def can_claim_cross_dept_step(user, task) -> bool:
    from tasks.models import WorkTask

    if not task.project_id or not task.project.is_cross_department:
        return False
    if task.assignee_mode != WorkTask.ASSIGNEE_DEPT_QUEUE:
        return False
    if task.assignee_id:
        return False
    if task.status != WorkTask.STATUS_PENDING_CLAIM:
        return False
    if is_director(user):
        return True
    if not can_receive_assigned_tasks(user):
        return False
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return False
    return task.target_department_id == profile.department_id


def can_view_project(user, project) -> bool:
    if not _has_tasks_module_access(user):
        return False
    if project.owner_id == user.id:
        return True
    if project.members.filter(pk=user.pk).exists():
        return True
    if is_cross_dept_dept_head_viewer(user, project):
        return True
    return False


def can_manage_project(user, project) -> bool:
    """Chủ dự án — thêm bước, duyệt handoff, duyệt bước."""
    if not _has_tasks_module_access(user):
        return False
    return project.owner_id == user.id


def can_view_task(user, task) -> bool:
    if not _has_tasks_module_access(user):
        return False
    if task.assignee_id == user.id or task.assigner_id == user.id:
        return True
    if task.project_id:
        if can_view_project(user, task.project):
            return True
        if can_claim_cross_dept_step(user, task):
            return True
    return False


def can_manage_assigned_task(user, task) -> bool:
    """Người giao việc — duyệt, hủy, giao lại. Bước dự án: chủ dự án."""
    if not _has_tasks_module_access(user):
        return False
    if task.project_id and can_manage_project(user, task.project):
        return True
    return task.assigner_id == user.id


def can_review_assigned_task(user, task) -> bool:
    """Duyệt hoàn thành / yêu cầu sửa — cần quyền sửa module Công việc."""
    if not can_manage_assigned_task(user, task):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_update_module
    return user_can_update_module(user, MODULE_TASKS)


def can_cancel_assigned_task(user, task) -> bool:
    """Hủy công việc — cần quyền xóa module Công việc."""
    if not can_manage_assigned_task(user, task):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_delete_module
    return user_can_delete_module(user, MODULE_TASKS)


def can_manage_project_steps(user, project) -> bool:
    """Thêm bước, giao lại — cần quyền thêm module Công việc."""
    if not can_manage_project(user, project):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_create_module
    return user_can_create_module(user, MODULE_TASKS)


def can_administer_project(user, project) -> bool:
    """Duyệt handoff, đóng dự án — cần quyền sửa module Công việc."""
    if not can_manage_project(user, project):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_update_module
    return user_can_update_module(user, MODULE_TASKS)
