"""Quy tắc đặt cơm — khung giờ cấu hình bởi HR (mặc định 16h–20h ngày hôm trước)."""

from datetime import datetime, time, timedelta

from django.utils import timezone

MEAL_ORDER_START = time(16, 0)
MEAL_ORDER_END = time(20, 0)
MEAL_ORDER_DAYS_BEFORE = 1


def get_meal_order_settings():
    from utilities.models import MealOrderSettings

    return MealOrderSettings.load()


def meal_order_window_for(meal_date):
    """Trả về (bắt đầu, kết thúc) cửa sổ đặt cho ngày ăn `meal_date`."""
    settings = get_meal_order_settings()
    order_day = meal_date - timedelta(days=settings.order_days_before)
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(order_day, settings.order_start_time), tz)
    end = timezone.make_aware(datetime.combine(order_day, settings.order_end_time), tz)
    return start, end


def is_meal_order_window_open(meal_date, *, now=None) -> bool:
    now = now or timezone.localtime()
    start, end = meal_order_window_for(meal_date)
    return start <= now <= end


def current_orderable_meal_date(*, now=None):
    """Ngày ăn có thể đặt ngay bây giờ (thường là ngày mai)."""
    now = now or timezone.localtime()
    today = now.date()
    candidate = today + timedelta(days=1)
    if is_meal_order_window_open(candidate, now=now):
        return candidate
    return None


def next_orderable_meal_date(*, now=None):
    """Ngày ăn sắp tới có cửa sổ đặt (kể cả chưa mở)."""
    now = now or timezone.localtime()
    today = now.date()
    for offset in (1, 2):
        candidate = today + timedelta(days=offset)
        start, _ = meal_order_window_for(candidate)
        if timezone.localtime(start) >= now or is_meal_order_window_open(candidate, now=now):
            return candidate
    return today + timedelta(days=1)


def format_order_window(meal_date) -> str:
    settings = get_meal_order_settings()
    order_day = meal_date - timedelta(days=settings.order_days_before)
    start_label = settings.order_start_time.strftime('%H:%M')
    end_label = settings.order_end_time.strftime('%H:%M')
    return f'{order_day.strftime("%d/%m/%Y")} từ {start_label} đến {end_label}'
