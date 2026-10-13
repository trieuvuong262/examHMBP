"""Dòng BOM thiết kế lấy mã, ĐVT và đơn giá từ kho NPL — cùng nguồn với phiếu xuất."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from kho_npl.catalog_labels import color_label, spec_label, unit_label
from kho_npl.models import Material
from kho_npl.services.uom import UomConversionError, factor_to_base
from kho_npl.stock_domain import STOCK_DOMAIN_NPL

from .workflow import WorkflowError


def spec_text(material: Material) -> str:
    parts = []
    if material.specification_id:
        parts.append(spec_label(material.specification))
    if material.color_id:
        parts.append(color_label(material.color))
    return ' · '.join(part for part in parts if part)[:255]


def _decimal_or_none(raw) -> Decimal | None:
    raw = (raw or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except Exception as exc:
        raise WorkflowError(f'Số không hợp lệ: {raw}') from exc
    if value < 0:
        raise WorkflowError('Không nhập số âm.')
    return value


def _unit_for(material: Material, raw_id: str):
    levels = list(material.specification.levels.all()) if material.specification_id else []
    allowed = {row.unit_id: row.unit for row in levels}
    if not allowed:
        return material.unit
    try:
        unit_id = int(raw_id)
    except (TypeError, ValueError):
        unit_id = material.unit_id
    unit = allowed.get(unit_id)
    if unit is None:
        raise WorkflowError(f'Đơn vị tính không thuộc quy cách của {material.name}.')
    return unit


def _price_for(material: Material, unit: Unit) -> Decimal:
    try:
        factor = factor_to_base(material, unit)
    except UomConversionError:
        factor = Decimal('1')
    return (Decimal(material.base_price or 0) * factor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def lines_from_post(post) -> list[dict]:
    """Mỗi dòng đã chọn mã kho được ghi lại tên, ĐVT và giá cơ bản của mã đó."""
    material_ids = post.getlist('line_material')
    unit_ids = post.getlist('line_unit')
    consumptions = post.getlist('line_consumption')
    prices = post.getlist('line_price')
    legacy_names = post.getlist('line_legacy_name')
    legacy_units = post.getlist('line_legacy_unit')

    wanted = [int(value) for value in material_ids if str(value).isdigit()]
    materials = {
        row.pk: row
        for row in Material.objects.filter(pk__in=wanted, stock_domain=STOCK_DOMAIN_NPL).select_related(
            'unit', 'color', 'specification',
        ).prefetch_related('specification__levels__unit')
    }

    lines = []
    for index, raw_id in enumerate(material_ids):
        consumption = _decimal_or_none(consumptions[index] if index < len(consumptions) else '')
        material = materials.get(int(raw_id)) if str(raw_id).isdigit() else None
        if str(raw_id).isdigit() and material is None:
            raise WorkflowError('Nguyên phụ liệu không thuộc kho NPL.')
        if material is not None:
            unit = _unit_for(material, unit_ids[index] if index < len(unit_ids) else '')
            lines.append({
                'material': material,
                'line_unit': unit,
                'material_name': material.name[:200],
                'spec': spec_text(material),
                'consumption': consumption,
                'unit': unit_label(unit)[:30],
                'unit_price': _price_for(material, unit),
                'is_main': True,
            })
            continue
        name = (legacy_names[index] if index < len(legacy_names) else '').strip()
        if not name:
            continue
        lines.append({
            'material': None,
            'line_unit': None,
            'material_name': name[:200],
            'spec': '',
            'consumption': consumption,
            'unit': (legacy_units[index] if index < len(legacy_units) else '').strip()[:30],
            'unit_price': _decimal_or_none(prices[index] if index < len(prices) else ''),
            'is_main': True,
        })
    return lines
