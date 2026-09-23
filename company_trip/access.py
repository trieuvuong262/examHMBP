"""Quyền menu Đăng ký du lịch (utilities.trip_schedule)."""

from hrm.menu_permissions import (
    user_can_create_menu,
    user_can_delete_menu,
    user_can_export_menu,
    user_can_menu_action,
    user_can_update_menu,
)
from hrm.permissions import is_portal_admin

TRIP_MODULE = 'utilities'
TRIP_MENU = 'trip_schedule'
TRIP_OPEN_ACTIONS = ('view', 'create', 'update', 'delete', 'export')
TRIP_MANAGE_ACTIONS = ('update', 'delete', 'export')


def trip_action_allowed(user, action: str) -> bool:
    if is_portal_admin(user):
        return True
    return user_can_menu_action(user, TRIP_MODULE, TRIP_MENU, action)


def trip_any_allowed(user, actions) -> bool:
    return any(trip_action_allowed(user, action) for action in actions)


def trip_can_open(user) -> bool:
    return trip_any_allowed(user, TRIP_OPEN_ACTIONS)


def trip_can_create(user) -> bool:
    return is_portal_admin(user) or user_can_create_menu(user, TRIP_MODULE, TRIP_MENU)


def trip_can_update(user) -> bool:
    return is_portal_admin(user) or user_can_update_menu(user, TRIP_MODULE, TRIP_MENU)


def trip_can_delete(user) -> bool:
    return is_portal_admin(user) or user_can_delete_menu(user, TRIP_MODULE, TRIP_MENU)


def trip_can_export(user) -> bool:
    return is_portal_admin(user) or user_can_export_menu(user, TRIP_MODULE, TRIP_MENU)


def trip_can_manage(user) -> bool:
    return trip_any_allowed(user, TRIP_MANAGE_ACTIONS)


def trip_ui_flags(user) -> dict:
    return {
        'can_create': trip_can_create(user),
        'can_update': trip_can_update(user),
        'can_delete': trip_can_delete(user),
        'can_export': trip_can_export(user),
        'can_manage': trip_can_manage(user),
    }
