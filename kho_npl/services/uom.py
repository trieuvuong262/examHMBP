from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError


QTY_QUANT = Decimal('0.001')
FACTOR_QUANT = Decimal('0.000001')
PRICE_QUANT = Decimal('0.000001')


class UomConversionError(ValueError):
    pass


def spec_levels(specification):
    if specification is None:
        return []
    return sorted(specification.levels.all(), key=lambda row: row.level)


def material_units(material):
    levels = spec_levels(material.specification)
    return [
        {
            'id': row.unit_id,
            'code': row.unit.code,
            'name': row.unit.name,
            'level': row.level,
            'factor': str(_factor_for_level(levels, row.level)),
            'is_base': row.level == 1,
        }
        for row in levels
    ]


def _factor_for_level(levels, target_level: int) -> Decimal:
    factor = Decimal('1')
    expected = 1
    for row in levels:
        if row.level != expected:
            raise UomConversionError('Các cấp quy cách phải liên tục từ cấp 1.')
        if row.level == 1:
            if row.qty_in_next_lower != Decimal('1'):
                raise UomConversionError('Hệ số cấp 1 phải bằng 1.')
        else:
            factor *= row.qty_in_next_lower
        if row.level == target_level:
            return factor.quantize(FACTOR_QUANT)
        expected += 1
    raise UomConversionError('ĐVT không thuộc quy cách của NPL.')


def factor_to_base(material, unit) -> Decimal:
    unit_id = getattr(unit, 'pk', unit)
    levels = spec_levels(material.specification)
    if not levels and unit_id == material.unit_id:
        return Decimal('1.000000')
    for row in levels:
        if row.unit_id == unit_id:
            return _factor_for_level(levels, row.level)
    raise UomConversionError(
        f'ĐVT không thuộc quy cách của {material.code}.'
    )


def to_base(material, qty, unit) -> Decimal:
    value = Decimal(str(qty or 0))
    return (value * factor_to_base(material, unit)).quantize(
        QTY_QUANT, rounding=ROUND_HALF_UP,
    )


def from_base(material, qty_base, unit) -> Decimal:
    factor = factor_to_base(material, unit)
    if factor <= 0:
        raise UomConversionError('Hệ số quy đổi phải lớn hơn 0.')
    return (Decimal(str(qty_base or 0)) / factor).quantize(
        QTY_QUANT, rounding=ROUND_HALF_UP,
    )


def package_qty(material, qty_base):
    """SL theo ĐVT chẵn lớn nhất. None nếu quy cách chỉ có ĐVT lẻ."""
    unit = getattr(material, 'package_unit', None)
    if unit is None:
        return None
    try:
        return from_base(material, qty_base, unit)
    except UomConversionError:
        return None


def price_to_base(price_entered, factor) -> Decimal:
    factor = Decimal(str(factor or 0))
    if factor <= 0:
        raise UomConversionError('Hệ số quy đổi phải lớn hơn 0.')
    return (Decimal(str(price_entered or 0)) / factor).quantize(
        PRICE_QUANT, rounding=ROUND_HALF_UP,
    )


def spec_unit_factors(specification) -> dict[str, str]:
    """unit_id → hệ số về ĐVT lẻ, dùng cho data-attribute trên form."""
    levels = spec_levels(specification)
    return {
        str(row.unit_id): str(_factor_for_level(levels, row.level))
        for row in levels
    }


def unit_factor_in_levels(levels, unit) -> Decimal | None:
    unit_id = getattr(unit, 'pk', unit)
    if not unit_id or not levels:
        return None
    try:
        for row in levels:
            if row.unit_id == unit_id:
                return _factor_for_level(levels, row.level)
    except UomConversionError:
        return None
    return None


def rebase_factor(old_unit, new_specification, old_specification=None) -> Decimal | None:
    """Số ĐVT lẻ mới tương ứng 1 đơn vị đang lưu. None nếu không quy đổi được."""
    old_id = getattr(old_unit, 'pk', old_unit)
    new_levels = spec_levels(new_specification)
    if not old_id or not new_levels:
        return None
    new_base_id = new_levels[0].unit_id
    if old_id == new_base_id:
        return Decimal('1')
    factor = unit_factor_in_levels(new_levels, old_id)
    if factor is not None:
        return factor
    if old_specification is not None:
        inverse = unit_factor_in_levels(spec_levels(old_specification), new_base_id)
        if inverse:
            return (Decimal('1') / inverse).quantize(FACTOR_QUANT)
    return None


def rebase_factor_from_cleaned_levels(old_unit, level1, level2=None, qty2=None, level3=None, qty3=None) -> Decimal | None:
    """Hệ số rebase từ các cấp đang nhập trên form quy cách."""
    old_id = getattr(old_unit, 'pk', old_unit)
    new_base_id = getattr(level1, 'pk', level1)
    if not old_id or not new_base_id:
        return None
    if old_id == new_base_id:
        return Decimal('1')
    factor = Decimal('1')
    if level2:
        factor *= Decimal(str(qty2 or 0))
        if getattr(level2, 'pk', level2) == old_id:
            return factor.quantize(FACTOR_QUANT) if factor > 0 else None
    if level3:
        factor *= Decimal(str(qty3 or 0))
        if getattr(level3, 'pk', level3) == old_id:
            return factor.quantize(FACTOR_QUANT) if factor > 0 else None
    return None


def rebase_qty(value, factor) -> Decimal:
    factor = Decimal(str(factor or 0))
    if factor <= 0:
        raise UomConversionError('Hệ số quy đổi phải lớn hơn 0.')
    return (Decimal(str(value or 0)) * factor).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def rebase_price(value, factor) -> Decimal:
    return price_to_base(value, factor)


def rebase_material_base(material, old_unit, factor):
    """Đổi tồn/lô/phiếu/BOM đang lưu theo ĐVT cũ sang ĐVT lẻ mới (giá ÷ factor, SL × factor)."""
    from django.apps import apps
    from django.db import models
    from django.db.models import F, Value

    from kho_npl.models import (
        Material,
        MaterialBatch,
        StockAdjustmentLine,
        StockBalance,
        StockDisposalLine,
        StockIssueLine,
        StockLedger,
        StockReceiptLine,
        StockReservation,
        StocktakeLine,
        StockTransferLine,
    )

    factor = Decimal(str(factor or 0))
    if factor <= 0:
        raise UomConversionError('Hệ số quy đổi phải lớn hơn 0.')
    if factor == 1:
        return

    def _multiply(qs, field_names):
        updates = {name: F(name) * Value(factor) for name in field_names}
        if updates:
            qs.update(**updates)

    def _divide(qs, field_names):
        updates = {name: F(name) / Value(factor) for name in field_names}
        if updates:
            qs.update(**updates)

    _multiply(StockBalance.objects.filter(material=material), ['quantity'])
    _multiply(MaterialBatch.objects.filter(material=material), ['quantity'])
    _divide(MaterialBatch.objects.filter(material=material), ['unit_price'])
    _multiply(StockLedger.objects.filter(material=material), ['qty_delta', 'balance_after'])
    _divide(StockLedger.objects.filter(material=material), ['unit_price'])
    _multiply(StockReservation.objects.filter(material=material), ['quantity'])

    Material.objects.filter(pk=material.pk).update(
        min_stock=F('min_stock') * Value(factor),
        base_price=F('base_price') / Value(factor),
    )

    line_configs = (
        (StockReceiptLine, 'received_qty'),
        (StockIssueLine, 'quantity'),
        (StockDisposalLine, 'quantity'),
        (StockTransferLine, 'quantity'),
        (StockAdjustmentLine, 'actual_qty'),
        (StocktakeLine, 'actual_qty'),
    )
    for model, entered_qty in line_configs:
        qs = model.objects.filter(material=material, line_unit=old_unit)
        qs.update(
            uom_factor=factor,
            qty_base=F(entered_qty) * Value(factor),
        )

    _divide(StockIssueLine.objects.filter(material=material), ['unit_price'])
    _multiply(StockAdjustmentLine.objects.filter(material=material), ['system_qty'])
    _multiply(StocktakeLine.objects.filter(material=material), ['system_qty'])

    try:
        BomLine = apps.get_model('san_xuat', 'BomLine')
    except LookupError:
        BomLine = None
    if BomLine is not None:
        _multiply(BomLine.objects.filter(material=material), ['qty'])

    for model in apps.get_models():
        field_names = {field.name for field in model._meta.fields}
        if 'material_code' not in field_names:
            continue
        qs = model.objects.filter(material_code__iexact=material.code)
        qty_fields = [
            field.name for field in model._meta.fields
            if isinstance(field, models.DecimalField)
            and (field.name == 'qty' or field.name.startswith('qty_') or field.name.endswith('_qty'))
        ]
        price_fields = [
            field.name for field in model._meta.fields
            if isinstance(field, models.DecimalField) and 'unit_price' in field.name
        ]
        _multiply(qs, qty_fields)
        _divide(qs, price_fields)


def validate_specification_levels(specification):
    levels = spec_levels(specification)
    if not levels:
        raise ValidationError('Quy cách phải có ít nhất một cấp ĐVT.')
    if len(levels) > 3:
        raise ValidationError('Quy cách chỉ được tối đa 3 cấp.')
    _factor_for_level(levels, levels[-1].level)
    if len({row.unit_id for row in levels}) != len(levels):
        raise ValidationError('Mỗi ĐVT chỉ được xuất hiện một lần trong quy cách.')
    return levels


def apply_line_conversion(line, qty) -> Decimal:
    unit = line.line_unit or line.material.unit
    factor = factor_to_base(line.material, unit)
    line.line_unit = unit
    line.uom_factor = factor
    line.qty_base = (Decimal(str(qty or 0)) * factor).quantize(
        QTY_QUANT, rounding=ROUND_HALF_UP,
    )
    return line.qty_base
