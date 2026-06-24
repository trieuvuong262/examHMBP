"""Điều kiện đăng ký web push portal — đặt cơm + thông báo công ty."""

from django.conf import settings

from hrm.menu_permissions import user_can_access_menu, user_can_create_menu
from hrm.module_permissions import MODULE_ANNOUNCEMENTS, MODULE_UTILITIES, user_can_access_module
from hrm.permissions import is_director
from reports.report_profile import is_production_report_user
from utilities.push_service import webpush_configured


def user_meal_push_eligible(user) -> bool:
    if not user_can_create_menu(user, MODULE_UTILITIES, 'meal_ordering'):
        return False
    return is_production_report_user(user)


def user_schedule_reminder_push_eligible(user) -> bool:
    return user_can_access_menu(user, MODULE_UTILITIES, 'schedule_reminder')


def user_portal_push_eligible(user) -> bool:
    """NV cần push: sản xuất (đặt cơm), nhắc lịch, hoặc có quyền xem Thông báo."""
    if not webpush_configured():
        return False
    if user_meal_push_eligible(user):
        return True
    if user_schedule_reminder_push_eligible(user):
        return True
    return user_can_access_module(user, MODULE_ANNOUNCEMENTS)


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
