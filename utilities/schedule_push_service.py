"""Web push nhắc lịch cá nhân — theo thứ trong tuần."""

from __future__ import annotations

import json
import logging

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from utilities.models import MealPushSubscription, ScheduleReminder, ScheduleReminderPushLog
from utilities.push_service import (
    _is_expired_push_subscription,
    _portal_base_url,
    send_push_to_subscription,
    webpush_configured,
)
from utilities.schedule_reminder_logic import should_fire_reminder

logger = logging.getLogger(__name__)


def _schedule_push_payload(reminder: ScheduleReminder) -> str:
    url = f'{_portal_base_url()}{reverse("home_portal")}#nhac-lich'
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
    local_today = timezone.localdate(now)
    reminders = (
        ScheduleReminder.objects.filter(is_active=True)
        .select_related('user')
        .order_by('id')
    )

    sent = skipped = failed = 0
    for reminder in reminders:
        if not should_fire_reminder(reminder, now):
            continue
        if ScheduleReminderPushLog.objects.filter(
            reminder=reminder,
            fire_date=local_today,
        ).exists():
            skipped += 1
            continue

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
