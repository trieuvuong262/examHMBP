"""Widget nhắc Tiện ích trên trang chủ portal."""

from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu, user_can_create_menu
from hrm.module_permissions import MODULE_UTILITIES

from utilities.meal_reminder import user_needs_meal_reminder
from utilities.meal_rules import format_order_window
from utilities.models import SalaryAdvanceDecline, SalaryAdvanceRequest
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


def get_utilities_pending_count(user) -> int:
    """Số việc Tiện ích cần xử lý — hiển thị badge menu."""
    return len(get_utilities_portal_widgets(user))


def meal_reminder_pending(user) -> bool:
    return user_needs_meal_reminder(user) is not None


def salary_reminder_pending(user) -> bool:
    return _salary_reminder_widget(user) is not None


def _meal_reminder_widget(user):
    meal_date = user_needs_meal_reminder(user)
    if not meal_date:
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
