"""Ghi nhận đồng ý nhận push portal — không hỏi lại sau khi user bấm Cho phép."""

from __future__ import annotations

from django.contrib.auth.models import User

from utilities.models import PortalPushConsentLog

_VALID_PERMISSIONS = {
    PortalPushConsentLog.PERMISSION_GRANTED,
    PortalPushConsentLog.PERMISSION_DENIED,
    PortalPushConsentLog.PERMISSION_DEFAULT,
}


def normalize_browser_permission(value: str | None) -> str:
    key = (value or '').strip().lower()
    if key in _VALID_PERMISSIONS:
        return key
    return PortalPushConsentLog.PERMISSION_DEFAULT


def user_has_push_consent(user: User) -> bool:
    return PortalPushConsentLog.objects.filter(user=user).exists()


def get_push_consent(user: User) -> PortalPushConsentLog | None:
    return PortalPushConsentLog.objects.filter(user=user).first()


def record_push_consent(
    user: User,
    *,
    browser_permission: str,
    push_subscribed: bool = False,
    user_agent: str = '',
) -> PortalPushConsentLog:
    permission = normalize_browser_permission(browser_permission)
    obj, _created = PortalPushConsentLog.objects.update_or_create(
        user=user,
        defaults={
            'browser_permission': permission,
            'push_subscribed': bool(push_subscribed),
            'user_agent': (user_agent or '')[:300],
        },
    )
    return obj


def clear_push_consent(user: User) -> int:
    deleted, _ = PortalPushConsentLog.objects.filter(user=user).delete()
    return deleted
