from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError


QTY_QUANT = Decimal('0.001')
FACTOR_QUANT = Decimal('0.000001')


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


def price_to_base(price_entered, factor) -> Decimal:
    factor = Decimal(str(factor or 0))
    if factor <= 0:
        raise UomConversionError('Hệ số quy đổi phải lớn hơn 0.')
    return (Decimal(str(price_entered or 0)) / factor).quantize(
        Decimal('0.000001'), rounding=ROUND_HALF_UP,
    )


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
