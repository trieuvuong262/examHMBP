"""Helper tối ưu đồng bộ incremental và trích xuất ảnh sản phẩm."""

from __future__ import annotations

from datetime import datetime

from django.db import models

SYNC_INTERVAL_CHOICES = (
    (5, 'Mỗi 5 phút'),
    (30, 'Mỗi 30 phút'),
    (360, 'Mỗi 6 giờ'),
    (720, 'Mỗi 12 giờ'),
    (1440, 'Mỗi 24 giờ'),
)

SYNC_INTERVAL_MINUTES = {value for value, _ in SYNC_INTERVAL_CHOICES}


def cron_hint_for_minutes(minutes: int) -> str:
    if minutes <= 5:
        return '*/5 * * * *'
    if minutes <= 30:
        return '*/30 * * * *'
    if minutes <= 360:
        return '0 */6 * * *'
    if minutes <= 720:
        return '0 */12 * * *'
    return '0 2 * * *'


def normalize_interval_minutes(value: int | str | None, *, default: int = 30) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return default
    return minutes if minutes in SYNC_INTERVAL_MINUTES else default


def needs_upsert(
    model: type[models.Model],
    *,
    retailer: str,
    kiotviet_id: int,
    incoming_modified: datetime | None,
) -> bool:
    """True nếu bản ghi chưa có hoặc modifiedDate mới hơn mirror."""
    existing = (
        model.objects.filter(retailer=retailer, kiotviet_id=kiotviet_id, is_deleted=False)
        .only('kv_modified_at')
        .first()
    )
    if existing is None:
        return True
    if incoming_modified is None:
        return True
    if existing.kv_modified_at is None:
        return True
    return incoming_modified > existing.kv_modified_at


def extract_product_image_urls(row: dict) -> list[str]:
    urls: list[str] = []
    for item in row.get('images') or []:
        if isinstance(item, str):
            url = item.strip()
        elif isinstance(item, dict):
            url = (
                item.get('Image')
                or item.get('image')
                or item.get('url')
                or ''
            ).strip()
        else:
            url = ''
        if url and url not in urls:
            urls.append(url)
    return urls
