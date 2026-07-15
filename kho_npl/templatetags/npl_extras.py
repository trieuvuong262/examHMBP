from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

from kho_npl.catalog_labels import color_label, spec_label, unit_label as catalog_unit_label
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


def format_npl_money(value) -> str:
    """Tiền VND, làm tròn đến đồng và phân cách hàng nghìn bằng dấu chấm."""
    d = _to_decimal(value)
    if d is None:
        return '—'
    rounded = d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return f'{rounded:,.0f}'.replace(',', '.') + 'đ'


def format_npl_money_exact(value) -> str:
    """Tiền VND giữ tối đa 2 số lẻ (cho tooltip) — VD: 41.726,22đ."""
    d = _to_decimal(value)
    if d is None:
        return '—'
    quantized = d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return format_npl_money(quantized)
    text = f'{quantized:,.2f}'  # 41,726.22
    text = text.replace(',', '\u0000').replace('.', ',').replace('\u0000', '.')
    return text + 'đ'


def unit_label(unit) -> str:
    """Nhãn ĐVT hiển thị — ưu tiên tên, không dùng mã."""
    return catalog_unit_label(unit)


@register.filter
def npl_unit(unit):
    return unit_label(unit)


@register.filter
def npl_spec(spec):
    return spec_label(spec)


@register.filter
def npl_color(color):
    return color_label(color)


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
def npl_money(value):
    return format_npl_money(value)


@register.filter
def npl_money_exact(value):
    return format_npl_money_exact(value)


@register.filter
def attachment_is_image(file_field):
    return is_image_attachment(file_field)
