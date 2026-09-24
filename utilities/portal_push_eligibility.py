"""Điều kiện đăng ký web push portal — đặt cơm + thông báo công ty."""

from django.conf import settings

from hrm.menu_permissions import user_can_create_menu
from hrm.module_permissions import MODULE_UTILITIES
from hrm.permissions import is_director
from reports.report_profile import is_production_report_user
from utilities.meal_rules import user_is_meal_order_eligible


def user_meal_push_eligible(user) -> bool:
    if not user_can_create_menu(user, MODULE_UTILITIES, 'meal_ordering'):
        return False
    if not user_is_meal_order_eligible(user):
        return False
    return is_production_report_user(user)


def user_schedule_reminder_push_eligible(user) -> bool:
    return bool(getattr(user, 'is_authenticated', False) and getattr(user, 'is_active', False))


def user_portal_push_eligible(user) -> bool:
    """Tắt vĩnh viễn hộp «Bật thông báo» và mọi đăng ký push trên portal."""
    return False


def user_portal_push_debug(user) -> bool:
    """Panel test push trang chủ — chỉ IT/admin thử nghiệm, không hiện cho Giám đốc."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if is_director(user):
        return False
    allowed = getattr(settings, 'PORTAL_PUSH_DEBUG_USERNAMES', None)
    if allowed is not None:
        return user.username in allowed
    return bool(getattr(user, 'is_staff', False))
