"""Giữ nhật ký thao tác trong 7 ngày gần nhất — xóa bản ghi cũ cho nhẹ DB."""

from __future__ import annotations

import time
from datetime import timedelta

from django.utils import timezone

ACTIVITY_LOG_RETENTION_DAYS = 7
PURGE_BATCH_SIZE = 2000
PURGE_INTERVAL_SECONDS = 3600

_last_purge_at = 0.0


def purge_old_activity_logs(
    *,
    days: int = ACTIVITY_LOG_RETENTION_DAYS,
    limit: int = PURGE_BATCH_SIZE,
) -> int:
    """Xóa tối đa `limit` bản ghi cũ hơn `days` ngày. Trả về số dòng đã xóa."""
    from audit.models import UserActivityLog

    cutoff = timezone.now() - timedelta(days=max(1, int(days)))
    ids = list(
        UserActivityLog.objects.filter(created_at__lt=cutoff)
        .order_by('created_at')
        .values_list('pk', flat=True)[:limit]
    )
    if not ids:
        return 0
    deleted, _ = UserActivityLog.objects.filter(pk__in=ids).delete()
    return deleted


def purge_all_old_activity_logs(
    *,
    days: int = ACTIVITY_LOG_RETENTION_DAYS,
    batch_size: int = PURGE_BATCH_SIZE,
) -> int:
    """Xóa hết bản ghi quá hạn, theo lô."""
    total = 0
    while True:
        deleted = purge_old_activity_logs(days=days, limit=batch_size)
        total += deleted
        if deleted < batch_size:
            return total


def maybe_purge_old_activity_logs() -> int:
    """Gọi định kỳ từ middleware — tối đa 1 lần/giờ mỗi worker."""
    global _last_purge_at
    now = time.monotonic()
    if now - _last_purge_at < PURGE_INTERVAL_SECONDS:
        return 0
    _last_purge_at = now
    try:
        return purge_old_activity_logs()
    except Exception:
        return 0
