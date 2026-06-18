"""Gửi web push nhắc đặt cơm."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from utilities.meal_reminder import user_needs_meal_reminder
from utilities.meal_rules import current_orderable_meal_date, format_order_window
from utilities.models import MealPushReminderLog, MealPushSubscription

logger = logging.getLogger(__name__)


def webpush_configured() -> bool:
    return bool(
        getattr(settings, 'WEBPUSH_VAPID_PUBLIC_KEY', '')
        and getattr(settings, 'WEBPUSH_VAPID_PRIVATE_KEY', '')
    )


def _portal_base_url() -> str:
    base = (getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '') or '').rstrip('/')
    if base:
        return base
    return 'https://portal.justplay.vn'


def _meal_push_payload(meal_date) -> str:
    meal_url = f'{_portal_base_url()}{reverse("utilities:meal_home")}'
    return json.dumps(
        {
            'title': 'Đặt cơm công ty',
            'body': (
                f'Đặt cơm cho ngày {meal_date.strftime("%d/%m/%Y")} '
                f'(khung {format_order_window(meal_date)}).'
            ),
            'url': meal_url,
            'tag': f'meal-reminder-{meal_date.isoformat()}',
        },
        ensure_ascii=False,
    )


def send_push_to_subscription(subscription: MealPushSubscription, payload: str) -> None:
    from pywebpush import webpush

    webpush(
        subscription_info=subscription.subscription_info(),
        data=payload,
        vapid_private_key=settings.WEBPUSH_VAPID_PRIVATE_KEY,
        vapid_claims={'sub': settings.WEBPUSH_VAPID_CLAIMS_EMAIL},
    )


def send_meal_reminder_pushes(*, now=None, dry_run: bool = False) -> dict:
    """
    Gửi push cho NV sản xuất đã đăng ký, trong khung 16h–20h, chưa đặc/từ chối.
  Trả về thống kê sent/skipped/failed.
    """
    if not webpush_configured():
        return {'sent': 0, 'skipped': 0, 'failed': 0, 'reason': 'webpush_not_configured'}

    now = now or timezone.localtime()
    if not current_orderable_meal_date(now=now):
        return {'sent': 0, 'skipped': 0, 'failed': 0, 'reason': 'outside_order_window'}

    User = get_user_model()
    users = (
        User.objects.filter(
            is_active=True,
            meal_push_subscriptions__isnull=False,
            profile__is_employed=True,
        )
        .distinct()
        .select_related('profile', 'profile__department')
    )

    sent = skipped = failed = 0
    for user in users:
        meal_date = user_needs_meal_reminder(user, now=now)
        if not meal_date:
            skipped += 1
            continue
        if MealPushReminderLog.objects.filter(employee=user, meal_date=meal_date).exists():
            skipped += 1
            continue

        subscriptions = list(MealPushSubscription.objects.filter(user=user))
        if not subscriptions:
            skipped += 1
            continue

        payload = _meal_push_payload(meal_date)
        delivered = False
        for subscription in subscriptions:
            if dry_run:
                delivered = True
                continue
            try:
                send_push_to_subscription(subscription, payload)
                delivered = True
            except Exception as exc:
                failed += 1
                status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
                if status_code in (404, 410):
                    subscription.delete()
                    logger.info('Removed expired push subscription %s', subscription.pk)
                else:
                    logger.warning('Push failed for user %s: %s', user.pk, exc)

        if delivered:
            if not dry_run:
                MealPushReminderLog.objects.get_or_create(
                    employee=user,
                    meal_date=meal_date,
                )
            sent += 1
        else:
            skipped += 1

    return {'sent': sent, 'skipped': skipped, 'failed': failed}
