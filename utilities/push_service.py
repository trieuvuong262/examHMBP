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

_vapid_instance = None


def _load_vapid():
    """pywebpush 2.x + cryptography 46: PEM string phải qua py_vapid.Vapid.from_pem."""
    global _vapid_instance
    if _vapid_instance is not None:
        return _vapid_instance

    from py_vapid import Vapid

    raw = (settings.WEBPUSH_VAPID_PRIVATE_KEY or '').strip()
    if not raw:
        raise ValueError('WEBPUSH_VAPID_PRIVATE_KEY is empty')
    if 'BEGIN' in raw:
        _vapid_instance = Vapid.from_pem(raw.encode('utf-8'))
    else:
        _vapid_instance = Vapid.from_string(raw)
    return _vapid_instance


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


def _push_exception_status(exc) -> int | None:
    response = getattr(exc, 'response', None)
    if response is not None:
        return getattr(response, 'status_code', None)
    return None


def _is_expired_push_subscription(exc) -> bool:
    return _push_exception_status(exc) in (404, 410)


def _is_wns_endpoint(endpoint: str) -> bool:
    return 'notify.windows.com' in (endpoint or '')


def _webpush_extra_headers(endpoint: str) -> dict:
    """
    Microsoft WNS (Edge/Chrome trên Windows) từ chối push nếu TTL=0 mà không có
    X-WNS-Cache-Policy=no-cache. Xem pywebpush#162.
    """
    if not _is_wns_endpoint(endpoint):
        return {}
    return {
        'X-WNS-Cache-Policy': 'no-cache',
        'X-WNS-Type': 'wns/raw',
    }


def send_push_to_subscription(subscription: MealPushSubscription, payload: str) -> None:
    from pywebpush import webpush

    endpoint = subscription.endpoint
    webpush(
        subscription_info=subscription.subscription_info(),
        data=payload,
        vapid_private_key=_load_vapid(),
        vapid_claims={'sub': settings.WEBPUSH_VAPID_CLAIMS_EMAIL},
        headers=_webpush_extra_headers(endpoint),
        ttl=0,
    )


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


def _test_meal_push_payload() -> str:
    meal_url = f'{_portal_base_url()}{reverse("utilities:meal_home")}'
    return json.dumps(
        {
            'title': 'Thử nhắc đặt cơm',
            'body': 'Đây là thông báo thử. Bạn sẽ nhận nhắc thật lúc 16:00 trong khung đặt cơm.',
            'url': meal_url,
            'tag': 'meal-reminder-test',
        },
        ensure_ascii=False,
    )


def send_test_meal_push(user) -> dict:
    """Gửi một push thử cho user hiện tại — xác nhận đăng ký hoạt động."""
    if not webpush_configured():
        return {'sent': 0, 'failed': 0, 'reason': 'webpush_not_configured'}

    subscriptions = list(MealPushSubscription.objects.filter(user=user))
    if not subscriptions:
        return {'sent': 0, 'failed': 0, 'reason': 'no_subscription'}

    payload = _test_meal_push_payload()
    sent = failed = 0
    for subscription in subscriptions:
        try:
            send_push_to_subscription(subscription, payload)
            sent += 1
        except Exception as exc:
            failed += 1
            if _is_expired_push_subscription(exc):
                subscription.delete()
            logger.warning('Test push failed for user %s: %s', user.pk, exc)

    return {'sent': sent, 'failed': failed}


def _test_schedule_push_payload() -> str:
    schedule_url = f'{_portal_base_url()}{reverse("tools:schedule_reminder")}'
    return json.dumps(
        {
            'title': 'Thử nhắc lịch',
            'body': 'Đây là thông báo thử — nhắc lịch đang hoạt động.',
            'url': schedule_url,
            'tag': 'schedule-reminder-test',
        },
        ensure_ascii=False,
    )


def send_test_schedule_push(user) -> dict:
    """Gửi push thử nhắc lịch — cùng pipeline đặt cơm."""
    if not webpush_configured():
        return {'sent': 0, 'failed': 0, 'reason': 'webpush_not_configured'}

    payload = _test_schedule_push_payload()
    delivered, _count, failed = _deliver_payload_to_user(user, payload)
    if not delivered and failed == 0:
        return {'sent': 0, 'failed': 0, 'reason': 'no_subscription'}
    return {'sent': 1 if delivered else 0, 'failed': failed}


def _schedule_push_payload(reminder) -> str:
    schedule_url = f'{_portal_base_url()}{reverse("tools:schedule_reminder")}'
    body = (reminder.body or '').strip()
    if not body:
        body = reminder.title
    return json.dumps(
        {
            'title': reminder.title,
            'body': body,
            'url': schedule_url,
            'tag': f'schedule-reminder-{reminder.pk}',
        },
        ensure_ascii=False,
    )


def _deliver_payload_to_user(user, payload: str, *, dry_run: bool = False) -> tuple[bool, int, int]:
    """Gửi push tới mọi subscription của user — cùng logic đặt cơm."""
    subscriptions = list(MealPushSubscription.objects.filter(user=user, user__is_active=True))
    if not subscriptions:
        return False, 0, 0

    delivered = False
    failed = 0
    for subscription in subscriptions:
        if dry_run:
            delivered = True
            continue
        try:
            send_push_to_subscription(subscription, payload)
            delivered = True
        except Exception as exc:
            failed += 1
            if _is_expired_push_subscription(exc):
                subscription.delete()
                logger.info('Removed expired push subscription %s', subscription.pk)
            else:
                logger.warning('Push failed for user %s: %s', user.pk, exc)
    return delivered, len(subscriptions), failed


def send_schedule_reminder_pushes(*, now=None, dry_run: bool = False) -> dict:
    """
    Gửi web push nhắc lịch — cùng pipeline đặt cơm (subscription + pywebpush).
    Cron mỗi phút; có grace window vài phút nếu cron trễ.
    """
    from django.db import transaction

    from utilities.models import ScheduleReminder, ScheduleReminderPushLog
    from utilities.schedule_reminder_logic import should_fire_reminder

    if not webpush_configured():
        return {'sent': 0, 'skipped': 0, 'failed': 0, 'reason': 'webpush_not_configured'}

    now = now or timezone.localtime()
    local_today = timezone.localdate(now)
    User = get_user_model()
    users = (
        User.objects.filter(
            is_active=True,
            meal_push_subscriptions__isnull=False,
            schedule_reminders__is_active=True,
        )
        .distinct()
        .prefetch_related('schedule_reminders')
    )

    sent = skipped = failed = 0
    for user in users:
        reminders = [r for r in user.schedule_reminders.all() if r.is_active]
        for reminder in reminders:
            if not should_fire_reminder(reminder, now):
                skipped += 1
                continue
            if ScheduleReminderPushLog.objects.filter(
                reminder=reminder,
                fire_date=local_today,
            ).exists():
                skipped += 1
                continue

            payload = _schedule_push_payload(reminder)
            delivered, _sub_count, sub_failed = _deliver_payload_to_user(
                user,
                payload,
                dry_run=dry_run,
            )
            failed += sub_failed

            if not delivered:
                skipped += 1
                continue

            if dry_run:
                sent += 1
                continue

            with transaction.atomic():
                ScheduleReminderPushLog.objects.get_or_create(
                    reminder=reminder,
                    fire_date=local_today,
                )
                if reminder.repeat_mode == ScheduleReminder.REPEAT_ONCE:
                    reminder.is_active = False
                    reminder.save(update_fields=['is_active', 'updated_at'])
            sent += 1

    return {'sent': sent, 'skipped': skipped, 'failed': failed}


def get_due_schedule_reminder_for_user(user, *, now=None) -> dict | None:
    """Nhắc đang đến giờ — dùng poll client khi user mở portal (giống thông báo)."""
    from utilities.models import ScheduleReminder
    from utilities.schedule_reminder_logic import is_reminder_due, reminder_fire_key

    now = now or timezone.localtime()
    for reminder in ScheduleReminder.objects.filter(user=user, is_active=True).order_by('remind_time'):
        if not is_reminder_due(reminder, now, grace_minutes=0):
            continue
        body = (reminder.body or '').strip() or reminder.title
        return {
            'reminder_id': reminder.pk,
            'fire_key': reminder_fire_key(reminder, now),
            'title': reminder.title,
            'body': body,
            'url': f'{_portal_base_url()}{reverse("tools:schedule_reminder")}',
        }
    return None


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
                if _is_expired_push_subscription(exc):
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
