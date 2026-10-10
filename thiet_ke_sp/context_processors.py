from __future__ import annotations

from django.core.cache import cache

from hrm.module_permissions import MODULE_THIET_KE_SP, user_can_access_module

BADGE_CACHE_SECONDS = 60
ACTIVE_COUNT_CACHE_KEY = 'tksp:active_count'
SIDEBAR_MENUS = ('dashboard', 'dossiers', 'kanban', 'approve', 'my_tasks', 'reports', 'settings')


def badge_cache_key(user_id: int) -> str:
    return f'tksp:badges:{user_id}'


def user_badges(user) -> dict[str, int]:
    from django.utils import timezone

    from .models import Notification, ProductDevelopment, Task
    from .presenters import APPROVAL_STATUSES

    key = badge_cache_key(user.pk)
    cached = cache.get(key)
    if cached is not None:
        return cached
    open_tasks = Task.objects.filter(assignee=user, state=Task.STATE_OPEN).exclude(
        dossier__status__in=('paused', 'cancelled', 'closed'),
    )
    data = {
        'tasks': open_tasks.count(),
        'overdue': open_tasks.filter(due_at__lt=timezone.now()).count(),
        'unread': Notification.objects.filter(user=user, is_read=False).count(),
        'approve': ProductDevelopment.objects.filter(approver=user, status__in=APPROVAL_STATUSES).count(),
    }
    cache.set(key, data, BADGE_CACHE_SECONDS)
    return data


def active_dossier_count() -> int:
    from .models import ProductDevelopment

    count = cache.get(ACTIVE_COUNT_CACHE_KEY)
    if count is None:
        count = ProductDevelopment.objects.exclude(status__in=('cancelled', 'closed')).count()
        cache.set(ACTIVE_COUNT_CACHE_KEY, count, BADGE_CACHE_SECONDS)
    return count


def member_access_cache_key(user_id: int) -> str:
    return f'tksp:member_access:{user_id}'


def member_only_access(user) -> bool:
    """Không có quyền module nhưng là thành viên của hồ sơ đang mở."""
    from .permissions import has_memberships

    key = member_access_cache_key(user.pk)
    allowed = cache.get(key)
    if allowed is None:
        allowed = has_memberships(user)
        cache.set(key, allowed, BADGE_CACHE_SECONDS)
    return allowed


def invalidate_user_badges(user) -> None:
    pk = getattr(user, 'pk', None)
    if pk:
        cache.delete_many([badge_cache_key(pk), member_access_cache_key(pk)])


def thiet_ke_sp_menu(request):
    from hrm.menu_permissions import user_can_access_resolved_menu

    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        return {'jp_can_thiet_ke_sp': False}
    if not user_can_access_module(user, MODULE_THIET_KE_SP):
        if not member_only_access(user):
            return {'jp_can_thiet_ke_sp': False}
        return {
            'jp_can_thiet_ke_sp': True,
            'tksp_menu': {key: key == 'dossiers' for key in SIDEBAR_MENUS},
            'tksp_my_task_count': 0,
            'tksp_overdue_count': 0,
            'tksp_unread_count': 0,
            'tksp_approve_count': 0,
            'tksp_active_count': 0,
        }
    badges = user_badges(user)
    menu = {key: user_can_access_resolved_menu(user, MODULE_THIET_KE_SP, key) for key in SIDEBAR_MENUS}
    return {
        'jp_can_thiet_ke_sp': True,
        'tksp_menu': menu,
        'tksp_my_task_count': badges['tasks'],
        'tksp_overdue_count': badges['overdue'],
        'tksp_unread_count': badges['unread'],
        'tksp_approve_count': badges.get('approve', 0),
        'tksp_active_count': active_dossier_count() if menu['dossiers'] else 0,
    }
