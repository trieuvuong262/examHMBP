from datetime import timedelta

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
