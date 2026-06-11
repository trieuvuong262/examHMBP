from decimal import Decimal, InvalidOperation

from django import template

from kho_npl.doc_attachment import attachment_is_image as is_image_attachment

register = template.Library()


def _to_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def format_npl_qty(value, max_decimals: int = 3) -> str:
    """Số nguyên không thập phân; có lẻ thì tối đa 3 chữ số (dấu phẩy VN)."""
    d = _to_decimal(value)
    if d is None:
        return '—'
    quantized = d.quantize(Decimal(10) ** -max_decimals)
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    text = f'{quantized:.{max_decimals}f}'.rstrip('0').rstrip('.')
    if '.' in text:
        whole, frac = text.split('.', 1)
        return f'{whole},{frac}'
    return text


def unit_label(unit) -> str:
    if unit is None:
        return ''
    code = getattr(unit, 'code', None)
    name = getattr(unit, 'name', None)
    return (code or name or str(unit)).strip()


@register.filter
def get_attr(obj, name):
    if isinstance(obj, dict):
        return obj.get(name, '')
    return getattr(obj, name, '')


@register.filter
def npl_qty(value, max_decimals=3):
    try:
        decimals = int(max_decimals)
    except (TypeError, ValueError):
        decimals = 3
    return format_npl_qty(value, decimals)


@register.filter
def npl_qty_with_unit(value, unit=None):
    qty = format_npl_qty(value)
    label = unit_label(unit)
    return f'{qty} {label}'.strip() if label else qty


@register.filter
def attachment_is_image(file_field):
    return is_image_attachment(file_field)
