"""Logic nhắc đặt cơm — dùng chung cho widget trang chủ và web push."""

from hrm.menu_permissions import user_can_access_menu, user_can_create_menu
from hrm.module_permissions import MODULE_UTILITIES
from reports.report_profile import is_production_report_user

from utilities.meal_rules import current_orderable_meal_date
from utilities.models import MealOrder, MealOrderDecline


def user_needs_meal_reminder(user, *, now=None):
    """
    Trả về ngày ăn cần nhắc nếu NV phải đặt cơm; None nếu không cần nhắc.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    if not user_can_access_menu(user, MODULE_UTILITIES, 'meal_ordering'):
        return None
    if not user_can_create_menu(user, MODULE_UTILITIES, 'meal_ordering'):
        return None
    if not is_production_report_user(user):
        return None

    meal_date = current_orderable_meal_date(now=now)
    if not meal_date:
        return None
    if MealOrder.objects.filter(employee=user, meal_date=meal_date).exists():
        return None
    if MealOrderDecline.objects.filter(employee=user, meal_date=meal_date).exists():
        return None
    return meal_date
