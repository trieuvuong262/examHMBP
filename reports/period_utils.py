"""Chu kỳ báo cáo VP — ngày / tuần / tháng."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from django.utils import timezone

from reports.week_utils import monday_of
from utilities.date_range_filter import (
    DATE_RANGE_DEFAULT_SPAN_DAYS as TEAM_MANAGEMENT_DEFAULT_SPAN_DAYS,
    DATE_RANGE_SPAN_CHOICES as TEAM_RANGE_SPAN_CHOICES,
    DATE_RANGE_SPAN_VALUES as TEAM_RANGE_SPAN_VALUES,
    match_date_range_span as match_team_range_span,
    parse_date_range_span_from_request as parse_team_range_span,
)

# Quản lý báo cáo (SX) mặc định 7 ngày — vẫn nằm trong preset chung 1/3/7/10/30.
TEAM_PRODUCTION_DEFAULT_SPAN_DAYS = 7

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
    # POST: ưu tiên body form (user đổi tab/kỳ rồi gửi) — tránh dính period cũ trên URL.
    if getattr(request, 'method', 'GET').upper() == 'POST':
        raw = (
            request.POST.get('period')
            or request.GET.get('period')
            or PERIOD_DAY
        )
    else:
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
    is_post = getattr(request, 'method', 'GET').upper() == 'POST'
    if period == PERIOD_MONTH:
        # POST: ưu tiên month/report_date trong form — tránh ghi đè nhầm tháng trên URL.
        if is_post:
            raw = (
                request.POST.get('month')
                or request.POST.get('report_date')
                or request.GET.get('month')
                or request.GET.get('date')
            )
        else:
            raw = (
                request.GET.get('month')
                or request.POST.get('month')
                or request.GET.get('date')
                or request.POST.get('report_date')
            )
        parsed = _parse_month_value(raw)
        return parsed or first_day_of_month(today)
    if period == PERIOD_WEEK:
        # POST: ưu tiên ngày tuần user chọn trên form. Trước đây GET ?date=...
        # thắng report_date → load báo cáo tuần A rồi save sang tuần B (trùng unique → 500).
        if is_post:
            raw = (
                request.POST.get('week_start')
                or request.POST.get('report_date')
                or request.GET.get('week')
                or request.GET.get('date')
            )
        else:
            raw = (
                request.GET.get('week')
                or request.POST.get('week_start')
                or request.GET.get('date')
                or request.POST.get('report_date')
            )
        parsed = _parse_iso_date(raw)
        if parsed:
            return monday_of(parsed)
        # Mặc định: tuần trước nếu còn hạn sửa, ngược lại tuần hiện tại
        last_week_monday = monday_of(today) - timedelta(days=7)
        last_week_end = last_week_monday + timedelta(days=6)
        # Hạn sửa tuần = hết ngày CN + 1 (tức thứ 2 tuần sau)
        if today <= last_week_end + timedelta(days=1):
            return last_week_monday
        return monday_of(today)
    if is_post:
        raw = (
            request.POST.get('report_date')
            or request.GET.get('date')
        )
    else:
        raw = (
            request.GET.get('date')
            or request.POST.get('report_date')
        )
    parsed = _parse_iso_date(raw)
    return parsed or today


def period_nav_date(request, period: str, anchor: date) -> date:
    """
    Ngày lịch dùng khi chuyển tab Ngày/Tuần/Tháng.

    Anchor lưu DB là đầu tuần/đầu tháng; nếu dùng trực tiếp cho tab Ngày sẽ nhảy
    sang kỳ cũ và báo nhầm «đã quá hạn chỉnh sửa».
    """
    today = timezone.localdate()
    explicit = _parse_iso_date(request.GET.get('date'))

    if period == PERIOD_WEEK:
        week_end = anchor + timedelta(days=6)
        if (
            explicit
            and explicit != anchor
            and anchor <= explicit <= week_end
        ):
            return explicit
        if anchor <= today <= week_end:
            return today
        if today < anchor:
            return anchor
        return week_end

    if period == PERIOD_MONTH:
        month_start = first_day_of_month(anchor)
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        if (
            explicit
            and explicit != month_start
            and month_start <= explicit <= month_end
        ):
            return explicit
        if month_start <= today <= month_end:
            return today
        if today < month_start:
            return month_start
        return month_end

    if explicit:
        return explicit
    return anchor


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
        return 'Chọn ngày bất kỳ trong tuần'
    if period == PERIOD_MONTH:
        return 'Tháng'
    return 'Ngày báo cáo'


def parse_team_date_range(request, *, default_span_days: int = TEAM_MANAGEMENT_DEFAULT_SPAN_DAYS) -> tuple[date, date]:
    """Khoảng thời gian lọc trên trang quản lý BC (SX/VP)."""
    today = timezone.localdate()
    date_to = _parse_iso_date(request.GET.get('to')) or today
    date_from = _parse_iso_date(request.GET.get('from'))
    span = parse_team_range_span(request, default=default_span_days)
    if not date_from:
        date_from = date_to - timedelta(days=max(span - 1, 0))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def parse_team_period_filter(request) -> str:
    """Lọc loại báo cáo VP trên trang quản lý BC — rỗng = tất cả."""
    raw = (request.GET.get('period') or '').strip().lower()
    if raw in (PERIOD_DAY, PERIOD_WEEK, PERIOD_MONTH):
        return raw
    return ''


def team_date_range_query_params(
    date_from: date,
    date_to: date,
    *,
    period: str = '',
    span: int | None = None,
) -> dict[str, str]:
    params = {
        'from': date_from.isoformat(),
        'to': date_to.isoformat(),
    }
    if period:
        params['period'] = period
    if span and span in TEAM_RANGE_SPAN_VALUES:
        params['span'] = str(span)
    return params


def team_range_query_params(period: str, date_from: date, date_to: date) -> dict[str, str]:
    """Giữ tương thích — trang quản lý BC dùng from/to và period lọc."""
    return team_date_range_query_params(date_from, date_to, period=period)


def report_anchor_display(report) -> str:
    """Nhãn mốc báo cáo trên bảng quản lý."""
    period = getattr(report, 'report_period', PERIOD_DAY) or PERIOD_DAY
    anchor = report.report_date
    if period == PERIOD_MONTH:
        return anchor.strftime('%m/%Y')
    if period == PERIOD_WEEK:
        end = anchor + timedelta(days=6)
        return f'{anchor.strftime("%d/%m")} – {end.strftime("%d/%m/%Y")}'
    return anchor.strftime('%d/%m/%Y')
