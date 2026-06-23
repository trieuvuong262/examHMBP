from datetime import timedelta

from django import template

from reports.period_utils import PERIOD_LABELS

register = template.Library()


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
