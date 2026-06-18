"""Context Tiện ích — web push + badge menu."""

from django.conf import settings

from hrm.menu_permissions import user_can_create_menu
from hrm.module_permissions import MODULE_UTILITIES
from reports.report_profile import is_production_report_user
from utilities.push_service import webpush_configured
from utilities.reminders import (
    get_utilities_pending_count,
    meal_reminder_pending,
    salary_reminder_pending,
)


def meal_push_context(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'jp_meal_push_eligible': False,
            'jp_webpush_public_key': '',
            'jp_utilities_pending_count': 0,
            'jp_utilities_meal_pending_count': 0,
            'jp_utilities_salary_pending_count': 0,
        }

    eligible = (
        webpush_configured()
        and user_can_create_menu(user, MODULE_UTILITIES, 'meal_ordering')
        and is_production_report_user(user)
    )
    return {
        'jp_meal_push_eligible': eligible,
        'jp_webpush_public_key': settings.WEBPUSH_VAPID_PUBLIC_KEY if eligible else '',
        'jp_utilities_pending_count': get_utilities_pending_count(user),
        'jp_utilities_meal_pending_count': int(meal_reminder_pending(user)),
        'jp_utilities_salary_pending_count': int(salary_reminder_pending(user)),
    }
