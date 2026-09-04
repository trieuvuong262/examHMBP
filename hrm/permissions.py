"""
Phân quyền thống nhất — JustPlay Portal.

Vai trò (Profile.role):
  EMPLOYEE         — Nhân viên
  TEAM_LEADER      — Tổ trưởng
  DIVISION_HEAD    — Trưởng bộ phận
  DEPARTMENT_HEAD  — Trưởng phòng
  DIRECTOR         — Giám đốc (staff portal khi lưu Profile)

Quản trị portal (menu Tuyển dụng, Đào tạo, Kiểm tra, Nhân sự):
  is_staff — HR / IT / Giám đốc
"""

from django.contrib.auth.models import User

ROLE_EMPLOYEE = 'EMPLOYEE'
ROLE_TEAM_LEADER = 'TEAM_LEADER'
ROLE_DIVISION_HEAD = 'DIVISION_HEAD'
ROLE_DEPARTMENT_HEAD = 'DEPARTMENT_HEAD'
ROLE_DIRECTOR = 'DIRECTOR'

# Alias tương thích code cũ
ROLE_HOD = ROLE_TEAM_LEADER
ROLE_GM = ROLE_DIRECTOR

ROLE_CHOICES = [
    (ROLE_EMPLOYEE, 'Nhân viên'),
    (ROLE_TEAM_LEADER, 'Tổ trưởng'),
    (ROLE_DIVISION_HEAD, 'Trưởng bộ phận'),
    (ROLE_DEPARTMENT_HEAD, 'Trưởng phòng'),
    (ROLE_DIRECTOR, 'Giám đốc'),
]

MANAGER_ROLES = {
    ROLE_TEAM_LEADER,
    ROLE_DIVISION_HEAD,
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
}
SUBORDINATE_MANAGER_ROLES = {
    ROLE_TEAM_LEADER,
    ROLE_DIVISION_HEAD,
    ROLE_DEPARTMENT_HEAD,
}


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
    from hrm.concurrent_positions import role_display_extended

    return role_display_extended(user)


def is_team_leader(user) -> bool:
    from hrm.concurrent_positions import user_has_role

    return user_has_role(user, ROLE_TEAM_LEADER)


def is_division_head(user) -> bool:
    """Trưởng bộ phận — Giám đốc / Trưởng phòng có quyền tương đương (ẩn)."""
    from hrm.concurrent_positions import user_is_division_head

    return user_is_division_head(user)


def is_department_head(user) -> bool:
    """Trưởng phòng — Giám đốc có quyền tương đương (ẩn) trên mọi phòng ban."""
    from hrm.concurrent_positions import user_is_department_head

    return user_is_department_head(user)


def is_director(user) -> bool:
    from hrm.concurrent_positions import user_is_director

    return user_is_director(user)


def is_hod(user) -> bool:
    """Tổ trưởng (alias tương thích)."""
    return is_team_leader(user)


def is_gm(user) -> bool:
    """Giám đốc (alias tương thích)."""
    return is_director(user)


def is_manager(user) -> bool:
    """Tổ trưởng, trưởng bộ phận hoặc giám đốc — quyền quản lý team."""
    from hrm.concurrent_positions import user_is_manager

    return user_is_manager(user)


def is_portal_admin(user) -> bool:
    """HR / quản trị portal — menu admin & @admin_only views."""
    return bool(getattr(user, 'is_authenticated', False) and user.is_staff)


def _has_reports_module_access(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import MODULE_REPORTS
    from hrm.role_permissions import user_can_view_module
    return user_can_view_module(user, MODULE_REPORTS)


GLOBAL_REPORT_VIEWER_USERNAMES = frozenset({'admin', 'ductn'})


def is_global_report_viewer(user) -> bool:
    """Xem mọi báo cáo — không đánh dấu hod_reviewed khi xem NV ngoài cấp dưới."""
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.module_permissions import bypass_department_modules
    if bypass_department_modules(user):
        return True
    return user.username.lower() in GLOBAL_REPORT_VIEWER_USERNAMES


def get_direct_manager_users(employee):
    """QL trực tiếp theo Nhân sự: Profile.subordinates + slot kiêm nhiệm."""
    if not employee or not getattr(employee, 'pk', None):
        return User.objects.none()

    from hrm.models import Profile, ProfileConcurrentPosition

    manager_ids = set(
        Profile.objects.filter(
            subordinates=employee,
            is_employed=True,
            user__is_active=True,
        ).values_list('user_id', flat=True),
    )
    manager_ids.update(
        ProfileConcurrentPosition.objects.filter(
            is_active=True,
            subordinates=employee,
            profile__is_employed=True,
            profile__user__is_active=True,
        ).values_list('profile__user_id', flat=True),
    )
    manager_ids.discard(employee.pk)
    if not manager_ids:
        return User.objects.none()

    role_rank = {
        ROLE_TEAM_LEADER: 1,
        ROLE_DIVISION_HEAD: 2,
        ROLE_DEPARTMENT_HEAD: 3,
        ROLE_DIRECTOR: 4,
    }
    managers = list(
        User.objects.filter(pk__in=manager_ids).select_related('profile'),
    )

    def _sort_key(mgr):
        profile = getattr(mgr, 'profile', None)
        role = getattr(profile, 'role', '') or ''
        name = (getattr(profile, 'full_name', None) or mgr.username or '').lower()
        return (role_rank.get(role, 99), name)

    managers.sort(key=_sort_key)
    # Giữ thứ tự đã sort (không reorder bằng queryset)
    ordered_ids = [m.pk for m in managers]
    preserved = {m.pk: m for m in managers}
    return [preserved[i] for i in ordered_ids]


def primary_direct_manager(employee):
    """QL gần nhất theo Nhân sự (ưu tiên tổ trưởng → … → giám đốc)."""
    managers = get_direct_manager_users(employee)
    return managers[0] if managers else None


def format_direct_managers_label(employee) -> str:
    managers = get_direct_manager_users(employee)
    if not managers:
        return ''
    labels = []
    for mgr in managers:
        profile = get_profile(mgr)
        labels.append(profile.full_name if profile and profile.full_name else mgr.username)
    return ', '.join(labels)


def can_view_report_statistics(user) -> bool:
    """Menu Thống kê báo cáo — chỉ khi nhóm quyền bật rõ submenu (không kế thừa mặc định).

    HR không cần tổ trưởng / cấp dưới vẫn xem toàn công ty để đánh giá KPI.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    from hrm.group_permissions import get_user_module_perm, module_perm_allows_view
    from hrm.menu_permissions import module_has_configured_menus
    from hrm.module_permissions import MODULE_REPORTS, bypass_department_modules
    from reports.navigation import MENU_REPORT_STATS

    if bypass_department_modules(user):
        return True
    if not _has_reports_module_access(user):
        return False

    mod_perm = get_user_module_perm(user, MODULE_REPORTS)
    if not module_has_configured_menus(mod_perm):
        return False
    menus = mod_perm.get('menus') or {}
    menu_perm = menus.get(MENU_REPORT_STATS)
    if not isinstance(menu_perm, dict):
        return False
    return module_perm_allows_view(menu_perm)


def has_company_wide_report_access(user) -> bool:
    """Xem danh sách / chi tiết báo cáo toàn công ty (admin, Giám đốc, hoặc Thống kê BC)."""
    if is_global_report_viewer(user):
        return True
    if is_director(user):
        return True
    return can_view_report_statistics(user)


def get_report_team_users(viewer):
    """Nhân viên cấp dưới — chỉ M2M đã cấu hình trong Nhân sự (chính + kiêm nhiệm)."""
    from hrm.concurrent_positions import get_manual_subordinate_users

    return get_manual_subordinate_users(viewer)


def get_team_report_members(viewer):
    """Danh sách NV trên trang team / nhập hộ — Giám đốc & global viewer thấy toàn công ty."""
    if has_company_wide_report_access(viewer):
        return (
            User.objects.filter(is_active=True, profile__is_employed=True)
            .exclude(pk=viewer.pk)
            .select_related('profile', 'profile__department')
            .order_by('profile__department__sort_order', 'profile__full_name', 'username')
        )
    return get_report_team_users(viewer)


def _viewer_can_see_employee_reports(viewer, employee) -> bool:
    if not _has_reports_module_access(viewer):
        return False
    if employee.pk == viewer.pk:
        return can_submit_daily_report(viewer)
    if has_company_wide_report_access(viewer):
        return True
    return get_report_team_users(viewer).filter(pk=employee.pk).exists()


def format_team_user_label(user) -> str:
    """Nhãn chọn nhân viên: Họ tên · Mã NS · account."""
    profile = get_profile(user)
    full_name = profile.full_name if profile and profile.full_name else user.username
    code = profile.employee_code if profile and profile.employee_code else '—'
    return f'{full_name} · {code} · {user.username}'


def has_report_subordinates(user) -> bool:
    return get_report_team_users(user).exists()


def can_view_team_reports(user) -> bool:
    """Xem báo cáo team — cấp dưới trực tiếp, Giám đốc, hoặc tài khoản xem toàn công ty."""
    if not _has_reports_module_access(user):
        return False
    if has_company_wide_report_access(user):
        return True
    return has_report_subordinates(user)


def can_submit_daily_report(user) -> bool:
    """Nộp báo cáo cá nhân — Giám đốc chỉ xem, không nộp (trừ tài khoản hệ thống)."""
    if not _has_reports_module_access(user):
        return False
    from hrm.module_permissions import MODULE_REPORTS, bypass_department_modules, user_can_create_module
    if not user_can_create_module(user, MODULE_REPORTS):
        return False
    if bypass_department_modules(user):
        return True
    return not is_director(user)


def can_view_user_report(viewer, report) -> bool:
    if not getattr(viewer, 'is_authenticated', False):
        return False
    return _viewer_can_see_employee_reports(viewer, report.employee)


def can_view_user_weekly_report(viewer, report) -> bool:
    if not getattr(viewer, 'is_authenticated', False):
        return False
    return _viewer_can_see_employee_reports(viewer, report.employee)


def can_review_user_weekly_report(viewer, report) -> bool:
    if report.employee_id == viewer.id:
        return False
    if not get_report_team_users(viewer).filter(pk=report.employee_id).exists():
        return False
    from hrm.module_permissions import MODULE_REPORTS, user_can_update_module
    return user_can_update_module(viewer, MODULE_REPORTS)


def can_review_user_report(viewer, report) -> bool:
    """Duyệt / phản hồi báo cáo cấp dưới trực tiếp."""
    if report.employee_id == viewer.id:
        return False
    if not get_report_team_users(viewer).filter(pk=report.employee_id).exists():
        return False
    from hrm.module_permissions import MODULE_REPORTS, user_can_update_module
    return user_can_update_module(viewer, MODULE_REPORTS)


def can_comment_on_user_report(viewer, report) -> bool:
    """Nhận xét báo cáo ngày — cấp dưới (review) hoặc Giám đốc mọi NV (SX/VP)."""
    if not getattr(viewer, 'is_authenticated', False):
        return False
    if report.employee_id == viewer.id:
        return True
    if can_review_user_report(viewer, report):
        return True
    if not is_director(viewer):
        return False
    if not can_view_user_report(viewer, report):
        return False
    from hrm.module_permissions import MODULE_REPORTS, user_can_update_module
    return user_can_update_module(viewer, MODULE_REPORTS)


def can_comment_on_user_weekly_report(viewer, report) -> bool:
    """Nhận xét báo cáo tuần — cấp dưới (review) hoặc Giám đốc mọi NV."""
    if not getattr(viewer, 'is_authenticated', False):
        return False
    if report.employee_id == viewer.id:
        return True
    if can_review_user_weekly_report(viewer, report):
        return True
    if not is_director(viewer):
        return False
    if not can_view_user_weekly_report(viewer, report):
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
    - Giám đốc (chính hoặc kiêm nhiệm): toàn công ty
    - Trưởng phòng tại bất kỳ slot: union NV các phòng ban đó
    - Trưởng bộ phận: union NV các bộ phận slot + cấp dưới
    - Tổ trưởng: union NV các bộ phận slot + cấp dưới thủ công
    """
    from hrm.concurrent_positions import effective_department_ids, effective_roles
    from hrm.models import Department

    profile = get_profile(assigner)
    if not profile:
        return User.objects.none()

    roles = effective_roles(assigner)
    if ROLE_DIRECTOR in roles or assigner.is_superuser:
        return _all_company_task_users(exclude_pk=assigner.pk)

    eligible_ids: set[int] = set()
    if ROLE_DEPARTMENT_HEAD in roles:
        for dept_id in effective_department_ids(assigner):
            dept = Department.objects.filter(pk=dept_id).first()
            if dept:
                eligible_ids.update(
                    _department_task_users(dept).values_list('pk', flat=True),
                )

    if ROLE_DIVISION_HEAD in roles:
        from hrm.concurrent_positions import effective_division_ids

        for div_id in effective_division_ids(assigner):
            qs = User.objects.filter(
                profile__division_id=div_id,
                profile__is_employed=True,
                is_active=True,
            )
            eligible_ids.update(qs.values_list('pk', flat=True))
        eligible_ids.update(
            get_report_team_users(assigner).values_list('pk', flat=True),
        )

    if ROLE_TEAM_LEADER in roles:
        eligible_ids.update(
            get_report_team_users(assigner).values_list('pk', flat=True),
        )

    if not eligible_ids:
        return User.objects.none()

    qs = User.objects.filter(pk__in=eligible_ids).select_related('profile')
    return _filter_task_recipient_users(qs, exclude_pk=assigner.pk)


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
    - Trưởng bộ phận / trưởng phòng: có phạm vi giao việc tương ứng
    - Giám đốc: quyền sửa module Công việc
    """
    if not _has_tasks_module_access(user):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_create_module
    if not user_can_create_module(user, MODULE_TASKS):
        return False

    from hrm.concurrent_positions import effective_department_ids, effective_roles

    roles = effective_roles(user)
    if ROLE_TEAM_LEADER in roles:
        return has_task_subordinates(user)
    if ROLE_DIVISION_HEAD in roles:
        from hrm.concurrent_positions import effective_division_ids

        return bool(effective_division_ids(user)) or has_task_subordinates(user)
    if ROLE_DEPARTMENT_HEAD in roles:
        return bool(effective_department_ids(user))
    if ROLE_DIRECTOR in roles:
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


CROSS_DEPT_CREATOR_ROLES = {ROLE_DIRECTOR, ROLE_DEPARTMENT_HEAD, ROLE_DIVISION_HEAD}


def can_create_cross_dept_project(user) -> bool:
    """Chỉ Giám đốc hoặc Trưởng bộ phận — cần quyền sửa module Công việc."""
    if not _has_tasks_module_access(user):
        return False
    from hrm.module_permissions import MODULE_TASKS, user_can_create_module
    if not user_can_create_module(user, MODULE_TASKS):
        return False
    from hrm.concurrent_positions import effective_roles

    return bool(effective_roles(user) & CROSS_DEPT_CREATOR_ROLES)


def can_create_any_project(user) -> bool:
    """Tạo dự án nội bộ hoặc liên phòng ban."""
    return can_create_internal_project(user) or can_create_cross_dept_project(user)


def is_cross_dept_dept_head_viewer(user, project) -> bool:
    """Trưởng bộ phận xem dự án liên phòng ban — Giám đốc xem tất cả."""
    if not project.is_cross_department:
        return False
    if is_director(user):
        return True
    from hrm.concurrent_positions import effective_department_ids, effective_roles

    roles = effective_roles(user)
    if not (roles & {ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD}):
        return False
    dept_ids = effective_department_ids(user)
    if not dept_ids:
        return False
    return project.departments.filter(pk__in=dept_ids).exists()


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
    from hrm.concurrent_positions import effective_department_ids

    dept_ids = effective_department_ids(user)
    if not dept_ids:
        return False
    return task.target_department_id in dept_ids


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
