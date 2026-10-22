from decimal import Decimal, ROUND_HALF_UP

from django import template

from cham_cong.calc import format_credit, format_minutes

register = template.Library()


@register.filter
def minutes_vi(value):
    if value in (None, ''):
        return format_minutes(0)
    return format_minutes(value)


@register.filter
def credit_vi(value):
    if value in (None, ''):
        return format_credit(None)
    return format_credit(value)


METHOD_LABELS = {
    'ip': 'WiFi công ty',
    'gps': 'Định vị',
    'manual': 'Bổ sung',
}


@register.filter
def method_vi(value):
    return METHOD_LABELS.get(value or '', '')


@register.filter
def vnd_vi(value):
    if value in (None, ''):
        return '0 đ'
    number = Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    sign = '-' if number < 0 else ''
    text = f'{abs(int(number)):,}'.replace(',', '.')
    return f'{sign}{text} đ'
