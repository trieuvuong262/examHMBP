"""Context Tiện ích — web push + badge menu."""

from django.conf import settings

from utilities.portal_push_eligibility import user_meal_push_eligible, user_portal_push_debug, user_portal_push_eligible
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
            'jp_portal_push_eligible': False,
            'jp_portal_push_debug': False,
            'jp_webpush_public_key': '',
            'jp_utilities_pending_count': 0,
            'jp_utilities_meal_pending_count': 0,
            'jp_utilities_salary_pending_count': 0,
        }

    meal_eligible = user_meal_push_eligible(user)
    portal_eligible = user_portal_push_eligible(user)
    return {
        'jp_meal_push_eligible': meal_eligible,
        'jp_portal_push_eligible': portal_eligible,
        'jp_portal_push_debug': user_portal_push_debug(user),
        'jp_webpush_public_key': settings.WEBPUSH_VAPID_PUBLIC_KEY if portal_eligible else '',
        'jp_utilities_pending_count': get_utilities_pending_count(user),
        'jp_utilities_meal_pending_count': int(meal_reminder_pending(user)),
        'jp_utilities_salary_pending_count': int(salary_reminder_pending(user)),
    }
