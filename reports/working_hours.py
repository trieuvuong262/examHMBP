"""Giờ làm việc dùng cho hạn sửa báo cáo SX.

Đồng hồ chạy liên tục T2 → T7 12:00; tạm dừng chiều thứ Bảy (từ 12:00)
và cả ngày Chủ nhật. Không trừ ngày lễ.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone

SATURDAY = 5
SUNDAY = 6
# Chiều thứ Bảy bắt đầu lúc 12:00 (giờ local).
SATURDAY_OFF_FROM = time(12, 0)


def to_local(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def is_off_moment(dt: datetime) -> bool:
    """True trong chiều thứ Bảy (từ 12:00) hoặc Chủ nhật."""
    local = to_local(dt)
    weekday = local.weekday()
    if weekday == SUNDAY:
        return True
    return weekday == SATURDAY and local.time() >= SATURDAY_OFF_FROM


def resume_working_moment(dt: datetime) -> datetime:
    """Nếu đang nghỉ T7 chiều / CN thì nhảy tới 00:00 thứ Hai kế."""
    local = to_local(dt)
    weekday = local.weekday()
    if weekday == SUNDAY:
        monday = local + timedelta(days=1)
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    if weekday == SATURDAY and local.time() >= SATURDAY_OFF_FROM:
        monday = local + timedelta(days=2)
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return local


def _saturday_noon(local_dt: datetime) -> datetime:
    """12:00 thứ Bảy của tuần chứa ``local_dt`` (T2–T7)."""
    sat = local_dt + timedelta(days=SATURDAY - local_dt.weekday())
    return sat.replace(hour=12, minute=0, second=0, microsecond=0)


def add_working_hours(start: datetime, hours: int | float) -> datetime:
    """Cộng ``hours`` giờ làm việc kể từ ``start`` (trừ chiều T7 và CN)."""
    remaining = timedelta(hours=float(hours))
    if remaining <= timedelta(0):
        return resume_working_moment(start)

    current = resume_working_moment(start)
    for _ in range(40):
        if remaining <= timedelta(0):
            return current
        segment_end = _saturday_noon(current)
        available = segment_end - current
        if remaining <= available:
            return current + remaining
        remaining -= available
        current = resume_working_moment(segment_end)
    return current + remaining
