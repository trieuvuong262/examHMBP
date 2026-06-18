"""Widget nhắc Tiện ích trên trang chủ portal."""

from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu, user_can_create_menu
from hrm.module_permissions import MODULE_UTILITIES
from reports.report_profile import is_production_report_user

from utilities.meal_rules import current_orderable_meal_date, format_order_window
from utilities.models import MealOrder, MealOrderDecline, SalaryAdvanceDecline, SalaryAdvanceRequest
from utilities.salary_rules import current_advance_month, is_salary_advance_open


def get_utilities_portal_widgets(user):
    widgets = []
    meal = _meal_reminder_widget(user)
    if meal:
        widgets.append(meal)
    salary = _salary_reminder_widget(user)
    if salary:
        widgets.append(salary)
    return widgets


def _meal_reminder_widget(user):
    if not user_can_access_menu(user, MODULE_UTILITIES, 'meal_ordering'):
        return None
    if not user_can_create_menu(user, MODULE_UTILITIES, 'meal_ordering'):
        return None
    if not is_production_report_user(user):
        return None

    meal_date = current_orderable_meal_date()
    if not meal_date:
        return None

    if MealOrder.objects.filter(employee=user, meal_date=meal_date).exists():
        return None
    if MealOrderDecline.objects.filter(employee=user, meal_date=meal_date).exists():
        return None

    return {
        'level': 'warning',
        'icon': 'bi-cup-hot-fill',
        'title': 'Đặt cơm công ty',
        'text': (
            f'Đặt cơm cho ngày {meal_date.strftime("%d/%m/%Y")} '
            f'(khung {format_order_window(meal_date)}). '
            f'Bấm «Không đặt» nếu không ăn cơm công ty.'
        ),
        'url': reverse('utilities:meal_home'),
        'action': 'Đặt cơm',
        'dismiss_url': reverse('utilities:meal_decline'),
        'dismiss_label': 'Không đặt',
    }


def _salary_reminder_widget(user):
    if not user_can_access_menu(user, MODULE_UTILITIES, 'salary_advance'):
        return None
    if not user_can_create_menu(user, MODULE_UTILITIES, 'salary_advance'):
        return None
    if not is_salary_advance_open():
        return None

    month = current_advance_month()
    if SalaryAdvanceRequest.objects.filter(employee=user, request_month=month).exists():
        return None
    if SalaryAdvanceDecline.objects.filter(employee=user, request_month=month).exists():
        return None

    return {
        'level': 'info',
        'icon': 'bi-cash-coin',
        'title': 'Ứng lương tháng này',
        'text': (
            f'Hôm nay mở đăng ký ứng lương tháng {month.strftime("%m/%Y")} '
            f'(tối đa 3.000.000đ). Bấm «Không ứng» nếu không có nhu cầu.'
        ),
        'url': reverse('utilities:salary_home'),
        'action': 'Ứng lương',
        'dismiss_url': reverse('utilities:salary_decline'),
        'dismiss_label': 'Không ứng',
    }
