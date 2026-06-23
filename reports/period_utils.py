"""Chu kỳ báo cáo VP — ngày / tuần / tháng."""

from __future__ import annotations

from datetime import date, datetime

from django.utils import timezone

from reports.week_utils import monday_of

PERIOD_DAY = 'day'
PERIOD_WEEK = 'week'
PERIOD_MONTH = 'month'

PERIOD_CHOICES = [
    (PERIOD_DAY, 'Ngày'),
    (PERIOD_WEEK, 'Tuần'),
    (PERIOD_MONTH, 'Tháng'),
]

PERIOD_LABELS = dict(PERIOD_CHOICES)


def parse_office_period(request) -> str:
    raw = (
        request.GET.get('period')
        or request.POST.get('period')
        or PERIOD_DAY
    )
    raw = (raw or PERIOD_DAY).strip().lower()
    if raw in (PERIOD_DAY, PERIOD_WEEK, PERIOD_MONTH):
        return raw
    return PERIOD_DAY


def first_day_of_month(value: date) -> date:
    return value.replace(day=1)


def anchor_date_for_period(value: date, period: str) -> date:
    if period == PERIOD_WEEK:
        return monday_of(value)
    if period == PERIOD_MONTH:
        return first_day_of_month(value)
    return value


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_month_value(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    for fmt in ('%Y-%m', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(text[: len(fmt.replace('%', '')) + 2], fmt).date()
            return first_day_of_month(parsed)
        except ValueError:
            continue
    try:
        if len(text) >= 7 and text[4] == '-':
            year = int(text[:4])
            month = int(text[5:7])
            return date(year, month, 1)
    except (ValueError, TypeError):
        return None
    return None


def parse_period_anchor_date(request, period: str) -> date:
    today = timezone.localdate()
    if period == PERIOD_MONTH:
        raw = (
            request.GET.get('month')
            or request.POST.get('month')
            or request.GET.get('date')
            or request.POST.get('report_date')
        )
        parsed = _parse_month_value(raw)
        return parsed or first_day_of_month(today)
    if period == PERIOD_WEEK:
        raw = (
            request.GET.get('week')
            or request.POST.get('week_start')
            or request.GET.get('date')
            or request.POST.get('report_date')
        )
        parsed = _parse_iso_date(raw)
        return monday_of(parsed) if parsed else monday_of(today)
    raw = (
        request.GET.get('date')
        or request.POST.get('report_date')
    )
    parsed = _parse_iso_date(raw)
    return parsed or today


def period_query_param(period: str, anchor: date) -> dict[str, str]:
    if period == PERIOD_MONTH:
        return {'period': period, 'month': anchor.strftime('%Y-%m')}
    if period == PERIOD_WEEK:
        return {'period': period, 'date': anchor.isoformat()}
    return {'period': period, 'date': anchor.isoformat()}


def period_date_input_name(period: str) -> str:
    if period == PERIOD_MONTH:
        return 'month'
    return 'report_date'


def period_date_input_type(period: str) -> str:
    if period == PERIOD_MONTH:
        return 'month'
    return 'date'


def period_date_input_value(period: str, anchor: date) -> str:
    if period == PERIOD_MONTH:
        return anchor.strftime('%Y-%m')
    return anchor.isoformat()


def period_intro_title(period: str) -> str:
    if period == PERIOD_WEEK:
        return 'Báo cáo VP — Tuần'
    if period == PERIOD_MONTH:
        return 'Báo cáo VP — Tháng'
    return 'Báo cáo VP'


def period_date_label(period: str) -> str:
    if period == PERIOD_WEEK:
        return 'Tuần (bắt đầu thứ 2)'
    if period == PERIOD_MONTH:
        return 'Tháng'
    return 'Ngày báo cáo'
