"""Web push nhắc lịch cá nhân."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from utilities.models import MealPushSubscription, ScheduleReminder
from utilities.push_service import (
    _is_expired_push_subscription,
    _portal_base_url,
    send_push_to_subscription,
    webpush_configured,
)

logger = logging.getLogger(__name__)

SCHEDULE_REMINDER_GRACE = timedelta(hours=24)


def _schedule_push_payload(reminder: ScheduleReminder) -> str:
    url = f'{_portal_base_url()}{reverse("utilities:schedule_reminder_home")}'
    body = (reminder.body or '').strip()
    if not body:
        body = reminder.title
    return json.dumps(
        {
            'title': reminder.title,
            'body': body,
            'url': url,
            'tag': f'schedule-reminder-{reminder.pk}',
        },
        ensure_ascii=False,
    )


def send_schedule_reminder_pushes(*, now=None, dry_run: bool = False) -> dict:
    if not webpush_configured():
        return {'sent': 0, 'skipped': 0, 'failed': 0, 'reason': 'webpush_not_configured'}

    now = now or timezone.now()
    window_start = now - SCHEDULE_REMINDER_GRACE
    reminders = (
        ScheduleReminder.objects.filter(
            is_active=True,
            push_sent_at__isnull=True,
            remind_at__lte=now,
            remind_at__gte=window_start,
        )
        .select_related('user')
        .order_by('remind_at')
    )

    sent = skipped = failed = 0
    for reminder in reminders:
        subscriptions = list(
            MealPushSubscription.objects.filter(user=reminder.user, user__is_active=True),
        )
        if not subscriptions:
            skipped += 1
            continue

        payload = _schedule_push_payload(reminder)
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
                    logger.warning(
                        'Schedule push failed reminder=%s user=%s: %s',
                        reminder.pk,
                        reminder.user_id,
                        exc,
                    )

        if delivered:
            if not dry_run:
                reminder.push_sent_at = now
                reminder.save(update_fields=['push_sent_at', 'updated_at'])
            sent += 1
        else:
            skipped += 1

    return {'sent': sent, 'skipped': skipped, 'failed': failed}
