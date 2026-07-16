"""Costing rollup: NVL + nhân công + phụ phí."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from kho_npl.services.batches import material_avg_price
from san_xuat.models import BomVersion, CostingSnapshot
from san_xuat.services.products import resolve_kv_product_ref

ZERO = Decimal('0')
QTY = Decimal('0.0001')
MONEY = Decimal('0.01')


@dataclass
class BomLineCost:
    line_id: int
    material_code: str
    material_name: str
    qty: Decimal
    scrap_pct: Decimal
    qty_with_scrap: Decimal
    unit_price: Decimal
    amount: Decimal
    size_code: str = ''
    unit_name: str = ''


@dataclass
class ProcessStepCost:
    step_id: int
    sequence: int
    process_name: str
    norm_per_hour: Decimal
    cost_per_hour: Decimal
    hours_per_piece: Decimal
    labor_amount: Decimal


@dataclass
class CostingResult:
    material_lines: list[BomLineCost] = field(default_factory=list)
    process_lines: list[ProcessStepCost] = field(default_factory=list)
    material_cost: Decimal = ZERO
    labor_cost: Decimal = ZERO
    overhead_pct: Decimal = ZERO
    overhead_cost: Decimal = ZERO
    total_cost: Decimal = ZERO
    sell_price: Decimal = ZERO
    margin: Decimal = ZERO
    product_code: str = ''
    product_name: str = ''


def _d(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def labor_cost_for_step(norm_per_hour, cost_per_hour) -> tuple[Decimal, Decimal]:
    """
    Nhân công / cái = cost_per_hour / norm_per_hour
    (= giờ/cái × chi phí giờ).
    """
    norm = _d(norm_per_hour)
    rate = _d(cost_per_hour)
    if norm <= 0:
        return ZERO, ZERO
    hours = (Decimal('1') / norm).quantize(Decimal('0.000001'))
    amount = (rate / norm).quantize(MONEY)
    return hours, amount


def compute_costing(bom: BomVersion) -> CostingResult:
    result = CostingResult(
        overhead_pct=_d(bom.overhead_pct),
        product_code=bom.tech_doc.product_code,
        product_name=bom.tech_doc.product_name,
    )

    material_total = ZERO
    for line in bom.lines.select_related('material', 'material__unit').all():
        unit_price = material_avg_price(line.material)
        qty_scrap = line.qty_with_scrap
        amount = (qty_scrap * unit_price).quantize(MONEY)
        material_total += amount
        unit_name = ''
        if line.material.unit_id:
            unit_name = line.material.unit.code or line.material.unit.name or ''
        result.material_lines.append(
            BomLineCost(
                line_id=line.pk,
                material_code=line.material.code,
                material_name=line.material.name,
                qty=_d(line.qty),
                scrap_pct=_d(line.scrap_pct),
                qty_with_scrap=qty_scrap,
                unit_price=unit_price,
                amount=amount,
                size_code=line.size_code or '',
                unit_name=unit_name,
            ),
        )

    labor_total = ZERO
    for step in bom.process_steps.all():
        hours, amount = labor_cost_for_step(step.norm_per_hour, step.cost_per_hour)
        labor_total += amount
        result.process_lines.append(
            ProcessStepCost(
                step_id=step.pk,
                sequence=step.sequence,
                process_name=step.process_name,
                norm_per_hour=_d(step.norm_per_hour),
                cost_per_hour=_d(step.cost_per_hour),
                hours_per_piece=hours,
                labor_amount=amount,
            ),
        )

    base = material_total + labor_total
    overhead = (base * result.overhead_pct / Decimal('100')).quantize(MONEY)
    total = (base + overhead).quantize(MONEY)

    ref = resolve_kv_product_ref(bom.tech_doc.product_code)
    sell = _d(ref.base_price) if ref else ZERO
    if ref and ref.name and not result.product_name:
        result.product_name = ref.name

    result.material_cost = material_total.quantize(MONEY)
    result.labor_cost = labor_total.quantize(MONEY)
    result.overhead_cost = overhead
    result.total_cost = total
    result.sell_price = sell.quantize(MONEY)
    result.margin = (sell - total).quantize(MONEY)
    return result


def save_costing_snapshot(bom: BomVersion, *, user=None, notes: str = '') -> CostingSnapshot:
    result = compute_costing(bom)
    return CostingSnapshot.objects.create(
        bom=bom,
        material_cost=result.material_cost,
        labor_cost=result.labor_cost,
        overhead_cost=result.overhead_cost,
        total_cost=result.total_cost,
        sell_price=result.sell_price,
        margin=result.margin,
        notes=notes or '',
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
