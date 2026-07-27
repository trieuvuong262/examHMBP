"""Ghi nhật ký thao tác IE master data."""

from __future__ import annotations

from san_xuat.ie_models import SxIeAuditLog


def log_ie_event(
    *,
    action: str,
    summary: str = '',
    object_type: str = '',
    object_id: str | int = '',
    object_repr: str = '',
    changes: dict | None = None,
    user=None,
) -> SxIeAuditLog:
    username = ''
    if user is not None and getattr(user, 'is_authenticated', False):
        username = getattr(user, 'username', '') or ''
    elif user is not None:
        username = getattr(user, 'username', '') or str(user)
    return SxIeAuditLog.objects.create(
        action=action,
        object_type=(object_type or '')[:40],
        object_id=str(object_id or '')[:80],
        object_repr=(object_repr or '')[:255],
        summary=(summary or '')[:500],
        changes=changes or {},
        user=user if getattr(user, 'pk', None) else None,
        username=username[:150],
    )
