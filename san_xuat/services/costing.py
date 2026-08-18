"""Costing rollup: NVL + nhân công + phụ phí."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from kho_npl.services.batches import material_avg_price
from san_xuat.models import BomVersion, CostingSnapshot
from san_xuat.services.products import resolve_product_ref

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
    overhead_amount: Decimal = ZERO
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


def labor_from_order_routing_lines(snaps, *, fallback_cost_per_hour: Decimal = ZERO) -> Decimal:
    """Nhân công / cái từ snapshot routing đơn.

    Ưu tiên: Tổng đơn giá đã lưu → SMV áp dụng × hệ số × SL/SP
    → (SMV giây / 3600) × chi phí giờ BOM (khi chưa nhập hệ số).
    Hệ số đơn giá vẫn theo VNĐ/phút: (SMV giây / 60) × hệ số.
    """
    total = ZERO
    rate = _d(fallback_cost_per_hour)
    for ln in snaps or []:
        qty = _d(getattr(ln, 'qty_per_garment', None) or 1)
        applied = _d(getattr(ln, 'applied_unit_smv', None))
        smv = _d(getattr(ln, 'total_operation_smv', None))
        if smv <= 0:
            smv = (qty * applied).quantize(Decimal('0.0001'))
        stored = _d(getattr(ln, 'total_unit_price', None))
        if stored > 0:
            total += stored
            continue
        factor = _d(getattr(ln, 'price_factor', None))
        if factor > 0 and smv > 0:
            total += ((smv / Decimal('60')) * factor).quantize(MONEY)
            continue
        if rate > 0 and smv > 0:
            total += ((smv / Decimal('3600')) * rate).quantize(MONEY)
    return total.quantize(MONEY)


def _avg_bom_cost_per_hour(bom: BomVersion) -> Decimal:
    rates = [
        _d(s.cost_per_hour)
        for s in bom.process_steps.all()
        if _d(s.cost_per_hour) > 0
    ]
    if not rates:
        return ZERO
    return (sum(rates, ZERO) / Decimal(len(rates))).quantize(MONEY)


def compute_costing_for_sales_line(so_line) -> CostingResult:
    """GTKH 1 dòng ĐĐH: NVL + phụ phí từ BOM; nhân công từ SMV áp dụng trên đơn."""
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.bom import get_active_bom, get_working_bom

    bom = getattr(so_line, 'bom_version', None)
    code = (getattr(so_line, 'product_code', None) or '').strip()
    if bom is None and code:
        doc = (
            ProductTechDoc.objects.filter(product_code__iexact=code, is_active=True).first()
            or ProductTechDoc.objects.filter(product_code__iexact=code).first()
        )
        if doc:
            bom = get_active_bom(doc) or get_working_bom(doc)
    if bom is None:
        empty = CostingResult(product_code=code, product_name=getattr(so_line, 'product_name', '') or '')
        snaps = list(so_line.routing_lines.all()) if getattr(so_line, 'routing_lines', None) else []
        empty.labor_cost = labor_from_order_routing_lines(snaps)
        empty.total_cost = empty.labor_cost
        return empty

    result = compute_costing(bom)
    snaps = list(
        so_line.routing_lines.select_related('work_center').order_by('seq_no', 'id')
    ) if getattr(so_line, 'routing_lines', None) else []
    if not snaps:
        return result

    fallback_rate = _avg_bom_cost_per_hour(bom)
    labor = labor_from_order_routing_lines(snaps, fallback_cost_per_hour=fallback_rate)
    result.process_lines = [
        ProcessStepCost(
            step_id=ln.pk,
            sequence=ln.seq_no or 0,
            process_name=ln.op_name_vi or ln.op_code or '',
            norm_per_hour=(
                (Decimal('3600') / ln.applied_unit_smv).quantize(Decimal('0.01'))
                if _d(ln.applied_unit_smv) > 0 else ZERO
            ),
            cost_per_hour=_d(ln.price_factor),
            hours_per_piece=(_d(ln.total_operation_smv) / Decimal('3600')).quantize(Decimal('0.000001')),
            labor_amount=(
                _d(ln.total_unit_price) if _d(ln.total_unit_price) > 0
                else labor_from_order_routing_lines([ln], fallback_cost_per_hour=fallback_rate)
            ),
        )
        for ln in snaps
    ]
    result.labor_cost = labor
    base = result.material_cost + labor
    pct_overhead = (base * result.overhead_pct / Decimal('100')).quantize(MONEY)
    overhead = (result.overhead_amount + pct_overhead).quantize(MONEY)
    result.overhead_cost = overhead
    result.total_cost = (base + overhead).quantize(MONEY)
    sell = result.sell_price
    result.margin = (sell - result.total_cost).quantize(MONEY)
    if getattr(so_line, 'product_name', None):
        result.product_name = so_line.product_name or result.product_name
    return result


def compute_costing(bom: BomVersion, *, routing=None) -> CostingResult:
    """Costing theo BOM: NVL từ dòng BOM; nhân công từ ProcessStep (hoặc từ routing xem thử)."""
    result = CostingResult(
        overhead_pct=_d(bom.overhead_pct),
        overhead_amount=_d(getattr(bom, 'overhead_amount', None)),
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
    if routing is not None:
        for idx, line in enumerate(
            routing.lines.select_related('work_center').order_by('seq_no', 'pk'),
            start=1,
        ):
            smv = _d(line.applied_unit_smv)
            if smv <= 0:
                smv = _d(line.library_unit_smv)
            norm = (Decimal('3600') / smv).quantize(Decimal('0.01')) if smv > 0 else ZERO
            rate = _d(line.price_factor)
            hours, amount = labor_cost_for_step(norm, rate)
            labor_total += amount
            result.process_lines.append(
                ProcessStepCost(
                    step_id=line.pk,
                    sequence=line.seq_no or idx * 10,
                    process_name=line.op_name_vi or line.op_code or '',
                    norm_per_hour=norm,
                    cost_per_hour=rate,
                    hours_per_piece=hours,
                    labor_amount=amount,
                ),
            )
    else:
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
    pct_overhead = (base * result.overhead_pct / Decimal('100')).quantize(MONEY)
    overhead = (result.overhead_amount + pct_overhead).quantize(MONEY)
    total = (base + overhead).quantize(MONEY)

    ref = resolve_product_ref(bom.tech_doc.product_code)
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


def list_costing_from_active_boms(*, include_draft: bool = False) -> list[tuple]:
    """C0: danh sách (doc, bom, CostingResult) cho hub giá thành."""
    from san_xuat.models import BomVersion, ProductTechDoc
    from san_xuat.services.bom import get_active_bom, get_working_bom

    rows: list[tuple] = []
    docs = ProductTechDoc.objects.filter(is_active=True).order_by('product_code')
    for doc in docs:
        bom = get_active_bom(doc)
        if not bom and include_draft:
            bom = get_working_bom(doc)
        if not bom:
            continue
        if not include_draft and bom.status != BomVersion.STATUS_ACTIVE:
            continue
        rows.append((doc, bom, compute_costing(bom)))
    return rows


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
