from __future__ import annotations

from django.core.cache import cache

from hrm.module_permissions import MODULE_RA_MAT_SP, user_can_access_module

BADGE_CACHE_SECONDS = 60


def badge_cache_key(user_id: int) -> str:
    return f'rmsp:badges:{user_id}'


def user_badges(user) -> dict[str, int]:
    from django.utils import timezone

    from .models import APPROVAL_STATUSES, FINAL_STATUSES, OPEN_TASK_STATUSES, LaunchPlan, LaunchTask, Status

    key = badge_cache_key(user.pk)
    cached = cache.get(key)
    if cached is not None:
        return cached
    open_tasks = LaunchTask.objects.filter(owner=user, status__in=OPEN_TASK_STATUSES).exclude(
        plan__status__in=FINAL_STATUSES + (Status.PAUSED,),
    )
    data = {
        'tasks': open_tasks.count(),
        'overdue': open_tasks.filter(due_date__lt=timezone.localdate()).count(),
        'approve': LaunchPlan.objects.filter(approver=user, status__in=APPROVAL_STATUSES).count(),
    }
    cache.set(key, data, BADGE_CACHE_SECONDS)
    return data


def invalidate_plan_badges(plan) -> None:
    ids = {plan.coordinator_id, plan.approver_id}
    ids.update(plan.tasks.exclude(owner=None).values_list('owner_id', flat=True))
    cache.delete_many([badge_cache_key(pk) for pk in ids if pk])


def ra_mat_sp_menu(request):
    from hrm.menu_permissions import user_can_access_resolved_menu

    from .permissions import SIDEBAR_MENUS, has_participation

    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        return {'jp_can_ra_mat_sp': False}
    if not user_can_access_module(user, MODULE_RA_MAT_SP):
        if not has_participation(user):
            return {'jp_can_ra_mat_sp': False}
        badges = user_badges(user)
        return {
            'jp_can_ra_mat_sp': True,
            'rmsp_menu': {key: key in ('my_tasks', 'approve') for key in SIDEBAR_MENUS},
            'rmsp_my_task_count': badges['tasks'],
            'rmsp_overdue_count': badges['overdue'],
            'rmsp_approve_count': badges['approve'],
        }
    badges = user_badges(user)
    return {
        'jp_can_ra_mat_sp': True,
        'rmsp_menu': {key: user_can_access_resolved_menu(user, MODULE_RA_MAT_SP, key) for key in SIDEBAR_MENUS},
        'rmsp_my_task_count': badges['tasks'],
        'rmsp_overdue_count': badges['overdue'],
        'rmsp_approve_count': badges['approve'],
    }
