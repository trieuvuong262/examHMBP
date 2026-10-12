from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django import template

from reports.office_content import office_report_summary_text
from reports.period_utils import PERIOD_LABELS
from reports.production_hourly import format_production_quantity
from reports.production_shift_policy import shift_badge_class
from reports.weekly_preview import file_attachment_preview

register = template.Library()


@register.filter
def prod_qty(value):
    return format_production_quantity(value)


@register.filter
def production_shift_badge_class(shift):
    return shift_badge_class(shift or '')


@register.filter
def office_report_summary(report):
    if not report:
        return ''
    if getattr(report, 'is_production_report', False):
        return ''
    return office_report_summary_text(report)


@register.filter
def attachment_file_preview(att):
    if not att:
        return {}
    return file_attachment_preview(att)


@register.filter
def report_period_badge_class(report):
    if not report:
        return 'bg-secondary-subtle text-secondary'
    period = getattr(report, 'report_period', 'day') or 'day'
    return f'jp-report-period-badge jp-report-period-badge--{period}'


@register.filter
def report_period_label(report):
    if not report:
        return ''
    period = getattr(report, 'report_period', 'day') or 'day'
    return PERIOD_LABELS.get(period, period)


@register.filter
def efficiency_pct_display(value, arg='2'):
    """Hiển thị hiệu suất % — mặc định 2 chữ số thập phân (vd. 93,81)."""
    if value is None:
        return '—'
    try:
        places = int(arg)
    except (TypeError, ValueError):
        places = 2
    if places < 0:
        places = 2
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return '—'
    quantizer = Decimal('1').scaleb(-places)
    rounded = number.quantize(quantizer)
    text = f'{rounded:.{places}f}'
    return text.replace('.', ',')


# (ngưỡng tối thiểu %, CSS class, khoảng hiển thị, mã xếp loại, nhận xét) — sắp giảm dần theo ngưỡng.
EFFICIENCY_GRADE_TIERS = (
    (140, 'is-g-a1', '≥140%', 'A1', 'Xuất sắc'),
    (130, 'is-g-ap', '130–139%', 'A+', 'Xuất sắc'),
    (120, 'is-g-a', '120–129%', 'A', 'Vượt'),
    (110, 'is-g-bp', '110–119%', 'B+', 'Vượt'),
    (100, 'is-g-b', '100–109%', 'B', 'Đạt'),
    (90, 'is-g-cp', '90–99%', 'C+', 'Đạt'),
    (80, 'is-g-c', '80–89%', 'C', 'Cần cải thiện'),
    (70, 'is-g-dp', '70–79%', 'D+', 'Cần cải thiện'),
    (None, 'is-g-d', '<70%', 'D', 'Không đạt'),
)


def _efficiency_tier(pct):
    if pct is None:
        return None
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return None
    for tier in EFFICIENCY_GRADE_TIERS:
        if tier[0] is None or value >= tier[0]:
            return tier
    return None


@register.filter
def summary_efficiency_class(pct):
    """CSS class jp-eff theo thang xếp loại 9 mức (A1 … D) của báo cáo SX."""
    tier = _efficiency_tier(pct)
    return tier[1] if tier else 'is-none'


@register.filter
def summary_efficiency_grade(pct):
    """Nhãn xếp loại, vd. «A – Vượt»; rỗng khi không có số liệu."""
    tier = _efficiency_tier(pct)
    return f'{tier[3]} – {tier[4]}' if tier else ''


@register.simple_tag
def efficiency_grade_tiers():
    return [
        {'min_pct': min_pct, 'css_class': css, 'range_label': rng, 'code': code, 'label': label}
        for min_pct, css, rng, code, label in EFFICIENCY_GRADE_TIERS
    ]


@register.filter
def report_anchor_display(report):
    if not report:
        return ''
    period = getattr(report, 'report_period', 'day') or 'day'
    anchor = report.report_date
    if period == 'month':
        return anchor.strftime('%m/%Y')
    if period == 'week':
        end = anchor + timedelta(days=6)
        return f'{anchor.strftime("%d/%m")} – {end.strftime("%d/%m/%Y")}'
    return anchor.strftime('%d/%m/%Y')
