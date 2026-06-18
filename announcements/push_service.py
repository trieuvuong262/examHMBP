"""Web push khi có thông báo công ty mới."""

from __future__ import annotations

import json
import logging

from django.contrib.auth import get_user_model
from django.urls import reverse

from announcements.models import Announcement
from hrm.module_permissions import MODULE_ANNOUNCEMENTS, user_can_access_module
from utilities.models import MealPushSubscription
from utilities.push_service import (
    _is_expired_push_subscription,
    _portal_base_url,
    send_push_to_subscription,
    webpush_configured,
)

logger = logging.getLogger(__name__)


def announcement_push_payload(announcement: Announcement) -> str:
    detail_url = f'{_portal_base_url()}{reverse("announcements:detail", kwargs={"pk": announcement.pk})}'
    body = (announcement.summary or '').strip() or 'Có thông báo mới — mở portal để xem chi tiết.'
    return json.dumps(
        {
            'title': announcement.title,
            'body': body[:240],
            'url': detail_url,
            'tag': f'announcement-{announcement.pk}',
        },
        ensure_ascii=False,
    )


def send_announcement_push(announcement: Announcement) -> dict:
    """Gửi push tới mọi thiết bị đã đăng ký của user có quyền xem Thông báo."""
    if not webpush_configured() or not announcement.is_active:
        return {'sent': 0, 'failed': 0, 'skipped': 0, 'reason': 'not_active_or_not_configured'}

    payload = announcement_push_payload(announcement)
    User = get_user_model()
    user_ids = list(
        User.objects.filter(
            is_active=True,
            meal_push_subscriptions__isnull=False,
        )
        .distinct()
        .values_list('pk', flat=True),
    )

    sent = failed = skipped = 0
    for user_id in user_ids:
        user = User.objects.get(pk=user_id)
        if not user_can_access_module(user, MODULE_ANNOUNCEMENTS):
            skipped += 1
            continue

        delivered = False
        for subscription in MealPushSubscription.objects.filter(user_id=user_id):
            try:
                send_push_to_subscription(subscription, payload)
                delivered = True
                sent += 1
            except Exception as exc:
                failed += 1
                if _is_expired_push_subscription(exc):
                    subscription.delete()
                logger.warning(
                    'Announcement push failed ann=%s user=%s: %s',
                    announcement.pk,
                    user_id,
                    exc,
                )

        if not delivered:
            skipped += 1

    return {'sent': sent, 'failed': failed, 'skipped': skipped}
