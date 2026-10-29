"""Quyền module Kế hoạch ra mắt = quyền menu (Phân quyền) × vai trò trên từng kế hoạch.

- «Kế hoạch ra mắt»: Xem / Thêm (tạo kế hoạch) / Sửa (cập nhật mọi kế hoạch) / Xóa (xóa nháp).
- Người điều phối được sửa kế hoạch của mình; người phụ trách cập nhật công việc được giao.
- «Chờ tôi duyệt»: Sửa = được chọn làm Người duyệt kế hoạch / Go-No-Go.
- «Thiết lập»: Sửa = chỉnh checklist mẫu.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from hrm.menu_permissions import (
    user_can_access_resolved_menu,
    user_can_create_menu,
    user_can_delete_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_RA_MAT_SP

from .models import FINAL_STATUSES, LaunchPlan, Status

M = MODULE_RA_MAT_SP
MENU_DASHBOARD = 'dashboard'
MENU_PLANS = 'plans'
MENU_CALENDAR = 'calendar'
MENU_MY_TASKS = 'my_tasks'
MENU_APPROVE = 'approve'
MENU_SETTINGS = 'settings'
SIDEBAR_MENUS = (MENU_DASHBOARD, MENU_PLANS, MENU_CALENDAR, MENU_MY_TASKS, MENU_APPROVE, MENU_SETTINGS)


def can_view_module(user) -> bool:
    return user_can_access_resolved_menu(user, M, MENU_PLANS)


def can_create(user) -> bool:
    return user_can_create_menu(user, M, MENU_PLANS)


def can_update(user) -> bool:
    return user_can_update_menu(user, M, MENU_PLANS)


def can_delete(user) -> bool:
    return user_can_delete_menu(user, M, MENU_PLANS)


def has_approve_permission(user) -> bool:
    return user_can_update_menu(user, M, MENU_APPROVE)


def can_manage_settings(user) -> bool:
    return user_can_update_menu(user, M, MENU_SETTINGS)


def is_coordinator(plan: LaunchPlan, user) -> bool:
    return bool(user and user.pk) and user.pk in (plan.coordinator_id, plan.created_by_id)


def is_participant(plan: LaunchPlan, user) -> bool:
    if is_coordinator(plan, user) or plan.approver_id == user.pk:
        return True
    return (
        plan.tasks.filter(Q(owner=user) | Q(collaborators=user)).exists()
        or plan.risks.filter(owner=user).exists()
        or plan.group_owners.filter(owner=user).exists()
    )


def can_view_plan(plan: LaunchPlan, user) -> bool:
    return can_view_module(user) or is_participant(plan, user)


def can_edit_plan(plan: LaunchPlan, user) -> bool:
    """Sửa thông tin chung, sản phẩm, công việc, rủi ro."""
    if plan.status in FINAL_STATUSES:
        return False
    return can_update(user) or (can_view_module(user) and is_coordinator(plan, user))


def can_edit_header(plan: LaunchPlan, user) -> bool:
    return can_edit_plan(plan, user) and plan.status in (
        Status.DRAFT, Status.PLAN_PENDING, Status.PREPARING, Status.AT_RISK, Status.PAUSED,
    )


def can_update_task(plan: LaunchPlan, task, user) -> bool:
    if plan.status in FINAL_STATUSES:
        return False
    if can_edit_plan(plan, user):
        return True
    return task.owner_id == user.pk and plan.status != Status.DRAFT


def is_plan_approver(plan: LaunchPlan, user) -> bool:
    return plan.approver_id == user.pk and has_approve_permission(user)


def can_delete_plan(plan: LaunchPlan, user) -> bool:
    return plan.status == Status.DRAFT and (can_delete(user) or (is_coordinator(plan, user) and can_create(user)))


def participant_plan_ids(user):
    from .models import LaunchPlanGroupOwner, LaunchRisk, LaunchTask

    return (
        set(LaunchPlan.objects.filter(Q(coordinator=user) | Q(approver=user)).values_list('pk', flat=True))
        | set(LaunchTask.objects.filter(Q(owner=user) | Q(collaborators=user)).values_list('plan_id', flat=True))
        | set(LaunchRisk.objects.filter(owner=user).values_list('plan_id', flat=True))
        | set(LaunchPlanGroupOwner.objects.filter(owner=user).values_list('plan_id', flat=True))
    )


def has_participation(user) -> bool:
    from .models import LaunchTask, OPEN_TASK_STATUSES

    if not getattr(user, 'is_authenticated', False):
        return False
    active = LaunchPlan.objects.exclude(status__in=FINAL_STATUSES)
    return (
        active.filter(Q(coordinator=user) | Q(approver=user)).exists()
        or LaunchTask.objects.filter(Q(owner=user) | Q(collaborators=user), status__in=OPEN_TASK_STATUSES).exclude(
            plan__status__in=FINAL_STATUSES).exists()
    )


PARTICIPANT_URLS = frozenset({'detail', 'action', 'my_tasks', 'approve_queue', 'task_file'})


def member_path_allowed(user, path: str) -> bool:
    """Middleware: người được giao việc / người duyệt vào được kế hoạch mình tham gia khi không có quyền menu."""
    from django.urls import Resolver404, resolve

    try:
        match = resolve(path)
    except Resolver404:
        return False
    if match.namespace != 'ra_mat_sp' or match.url_name not in PARTICIPANT_URLS:
        return False
    if match.url_name in ('my_tasks', 'approve_queue'):
        return has_participation(user)
    if match.url_name == 'task_file':
        from .models import LaunchTaskFile

        plan_id = LaunchTaskFile.objects.filter(pk=match.kwargs.get('pk')).values_list('task__plan_id', flat=True).first()
        return plan_id in participant_plan_ids(user)
    return match.kwargs.get('pk') in participant_plan_ids(user)


def _matrix_allows_approve(matrix: dict) -> bool:
    module = (matrix or {}).get(M) or {}
    menus = module.get('menus')
    if isinstance(menus, dict) and menus:
        return bool((menus.get(MENU_APPROVE) or {}).get('update'))
    return bool(module.get('update'))


def approver_candidates():
    from hrm.group_permissions import permissions_from_legacy_role
    from hrm.models import PermissionGroup, Profile

    User = get_user_model()
    group_ids = [g.pk for g in PermissionGroup.objects.all() if _matrix_allows_approve(g.get_permissions())]
    legacy_roles = [
        role for role in Profile.objects.filter(permission_group__isnull=True).values_list('role', flat=True).distinct()
        if _matrix_allows_approve(permissions_from_legacy_role(role))
    ]
    rough = (
        User.objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(username='admin')
            | Q(profile__permission_group_id__in=group_ids)
            | Q(profile__permission_group__isnull=True, profile__role__in=legacy_roles)
        )
        .select_related('profile')
        .order_by('profile__full_name', 'username')
        .distinct()
    )
    return [u for u in rough if has_approve_permission(u)]
