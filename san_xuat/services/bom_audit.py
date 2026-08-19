"""Ghi nhật ký thao tác BOM."""

from __future__ import annotations


def log_bom_event(
    *,
    bom,
    action: str,
    summary: str = '',
    changes: dict | None = None,
    user=None,
):
    from san_xuat.models import SxBomAuditLog

    username = ''
    if user is not None:
        username = getattr(user, 'username', '') or str(user)

    return SxBomAuditLog.objects.create(
        bom=bom,
        action=action,
        summary=(summary or '')[:500],
        changes=changes or {},
        user=user if getattr(user, 'pk', None) else None,
        username=username[:150],
    )
