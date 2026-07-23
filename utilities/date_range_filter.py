"""Preset khoảng ngày chung cho bộ lọc Từ ngày — Đến ngày trên toàn portal."""

from __future__ import annotations

from datetime import date, timedelta

DATE_RANGE_SPAN_CHOICES = (
    (1, '1 ngày'),
    (3, '3 ngày'),
    (7, '7 ngày'),
    (10, '10 ngày'),
    (30, '30 ngày'),
)
DATE_RANGE_SPAN_VALUES = frozenset(v for v, _ in DATE_RANGE_SPAN_CHOICES)
DATE_RANGE_DEFAULT_SPAN_DAYS = 3


def parse_date_range_span(raw, *, default: int = DATE_RANGE_DEFAULT_SPAN_DAYS) -> int:
    """Parse query `span` → số ngày hợp lệ (1/3/7/10/30)."""
    value = (raw or '').strip() if isinstance(raw, str) else raw
    if isinstance(value, str) and value.isdigit():
        days = int(value)
        if days in DATE_RANGE_SPAN_VALUES:
            return days
    if isinstance(value, int) and value in DATE_RANGE_SPAN_VALUES:
        return value
    if default in DATE_RANGE_SPAN_VALUES:
        return default
    return DATE_RANGE_DEFAULT_SPAN_DAYS


def parse_date_range_span_from_request(request, *, default: int = DATE_RANGE_DEFAULT_SPAN_DAYS) -> int:
    return parse_date_range_span(getattr(request, 'GET', {}).get('span'), default=default)


def match_date_range_span(date_from: date | None, date_to: date | None) -> int | None:
    """Preset khớp khoảng from→to, hoặc None nếu tùy chỉnh."""
    if not date_from or not date_to:
        return None
    days = (date_to - date_from).days + 1
    if days in DATE_RANGE_SPAN_VALUES:
        return days
    return None


def date_range_from_span(date_to: date, span_days: int) -> date:
    span = max(1, int(span_days))
    return date_to - timedelta(days=span - 1)


def date_range_span_context(
    date_from: date | None = None,
    date_to: date | None = None,
    *,
    span: int | None = None,
) -> dict:
    """Context cho template bộ lọc khoảng ngày."""
    matched = span if span in DATE_RANGE_SPAN_VALUES else match_date_range_span(date_from, date_to)
    return {
        'range_span': matched,
        'range_span_choices': DATE_RANGE_SPAN_CHOICES,
    }
