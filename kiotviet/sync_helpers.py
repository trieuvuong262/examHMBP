"""Helper tối ưu đồng bộ incremental và trích xuất ảnh sản phẩm."""

from __future__ import annotations

from datetime import datetime

from django.db import models

# Sentinel: 3 lần/ngày lúc 06:00, 12:00, 19:00 (timezone máy chủ, Asia/Ho_Chi_Minh).
SYNC_INTERVAL_THRICE_DAILY = 481
DEFAULT_SYNC_INTERVAL_MINUTES = SYNC_INTERVAL_THRICE_DAILY
CRON_THRICE_DAILY = '0 6,12,19 * * *'

SYNC_INTERVAL_CHOICES = (
    (SYNC_INTERVAL_THRICE_DAILY, '3 lần/ngày · 6h · 12h · 19h'),
    (5, 'Mỗi 5 phút'),
    (30, 'Mỗi 30 phút'),
    (360, 'Mỗi 6 giờ'),
    (720, 'Mỗi 12 giờ'),
    (1440, 'Mỗi 24 giờ'),
)

SYNC_INTERVAL_MINUTES = {value for value, _ in SYNC_INTERVAL_CHOICES}


def cron_hint_for_minutes(minutes: int) -> str:
    if minutes == SYNC_INTERVAL_THRICE_DAILY:
        return CRON_THRICE_DAILY
    if minutes <= 5:
        return '*/5 * * * *'
    if minutes <= 30:
        return '*/30 * * * *'
    if minutes <= 360:
        return '0 */6 * * *'
    if minutes <= 720:
        return '0 */12 * * *'
    return '0 2 * * *'


def normalize_interval_minutes(
    value: int | str | None,
    *,
    default: int = DEFAULT_SYNC_INTERVAL_MINUTES,
) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return default
    return minutes if minutes in SYNC_INTERVAL_MINUTES else default


def clip_text(value, max_length: int | None) -> str:
    """Cắt chuỗi về max_length để tránh DataError varchar."""
    if value is None:
        text = ''
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text


def clip_charfield_defaults(model: type[models.Model], defaults: dict) -> dict:
    """Cắt mọi CharField trong defaults theo max_length của model."""
    if not defaults:
        return defaults
    clipped = dict(defaults)
    for field in model._meta.concrete_fields:
        name = field.name
        if name not in clipped:
            continue
        max_len = getattr(field, 'max_length', None)
        if not max_len:
            continue
        value = clipped[name]
        if value is None:
            continue
        clipped[name] = clip_text(value, max_len)
    return clipped


def kv_update_or_create(model: type[models.Model], **kwargs):
    defaults = kwargs.get('defaults')
    if defaults is not None:
        kwargs['defaults'] = clip_charfield_defaults(model, defaults)
    return model.objects.update_or_create(**kwargs)


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
