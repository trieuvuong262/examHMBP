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


@register.filter
def summary_efficiency_class(pct):
    """CSS class jp-eff cho thang màu 4 mức trên báo cáo tổng hợp SX."""
    if pct is None:
        return 'is-none'
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return 'is-none'
    if value >= 120:
        return 'is-high'
    if value >= 100:
        return 'is-norm'
    if value >= 80:
        return 'is-ok'
    return 'is-low'


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
