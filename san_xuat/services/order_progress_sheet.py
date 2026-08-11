"""Phiếu theo dõi tiến độ đơn (size × công đoạn mẫu cố định)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductionStat,
    SxWorkCenter,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.progress_template import (
    WC_SEED,
    progress_groups_with_steps,
    progress_steps,
    step_by_key,
)


def _q(v) -> Decimal:
    return Decimal(str(v or 0))


def ensure_progress_work_centers(*, deactivate_others: bool = False) -> list[SxWorkCenter]:
    """Tạo/cập nhật 6 tổ chuẩn (Cắt → Giao hàng thành phẩm)."""
    out: list[SxWorkCenter] = []
    keep = {code for code, _n, _t in WC_SEED}
    for code, name, team in WC_SEED:
        wc, created = SxWorkCenter.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'team_label': team,
                'is_active': True,
                'is_demo': False,
            },
        )
        update_fields: list[str] = []
        if (wc.name or '') != name:
            wc.name = name
            update_fields.append('name')
        if (wc.team_label or '') != team:
            wc.team_label = team
            update_fields.append('team_label')
        if not wc.is_active:
            wc.is_active = True
            update_fields.append('is_active')
        if wc.is_demo:
            wc.is_demo = False
            update_fields.append('is_demo')
        if update_fields:
            wc.save(update_fields=update_fields)
        out.append(wc)
    if deactivate_others:
        SxWorkCenter.objects.filter(is_demo=False, is_active=True).exclude(
            code__in=keep,
        ).update(is_active=False)
    return out


def standard_work_centers_qs():
    """QuerySet tổ/chuyền chuẩn cho Năng lực SX / Công việc tổ."""
    ensure_progress_work_centers()
    codes = [code for code, _n, _t in WC_SEED]
    # Giữ thứ tự theo mẫu
    by_code = {
        wc.code: wc
        for wc in SxWorkCenter.objects.filter(code__in=codes, is_demo=False)
    }
    return [by_code[c] for c in codes if c in by_code]


def work_center_map() -> dict[str, SxWorkCenter]:
    ensure_progress_work_centers()
    codes = {s.work_center_code for s in progress_steps()}
    return {
        wc.code: wc
        for wc in SxWorkCenter.objects.filter(code__in=codes, is_demo=False)
    }


@dataclass
class SizePlanRow:
    size_label: str
    qty: Decimal
    color_labels: list[str] = field(default_factory=list)


@dataclass
class SheetCell:
    process_key: str
    process_label: str
    done: Decimal
    remaining: Decimal


@dataclass
class DailyCell:
    process_key: str
    size_label: str
    qty: Decimal


@dataclass
class DailyRow:
    stat_date: date
    cells: dict[tuple[str, str], Decimal]  # (size, process_key) -> qty


@dataclass
class ProgressSheet:
    mo: SxProductionOrder
    order_code: str
    product_code: str
    product_name: str
    total_qty: Decimal
    color_summary: str
    sizes: list[SizePlanRow]
    groups: list[tuple]  # (ProgressGroup, list[ProgressStepDef])
    # size_label -> process_key -> SheetCell
    matrix: dict[str, dict[str, SheetCell]]
    daily_rows: list[DailyRow]
    size_totals_done: dict[str, Decimal]  # optional rollup
    # Hàng sẵn cho template
    done_rows: list[dict] = field(default_factory=list)
    remain_rows: list[dict] = field(default_factory=list)
    daily_display: list[dict] = field(default_factory=list)


def _size_plans(mo: SxProductionOrder) -> list[SizePlanRow]:
    lines = list(
        SxProductionOrderLine.objects.filter(production_order=mo).order_by('size_label', 'id')
    )
    by_size: dict[str, SizePlanRow] = {}
    for ln in lines:
        size = (ln.size_label or '').strip() or '—'
        qty = _q(ln.qty)
        if qty <= 0:
            continue
        row = by_size.get(size)
        if not row:
            row = SizePlanRow(size_label=size, qty=Decimal('0'), color_labels=[])
            by_size[size] = row
        row.qty += qty
        color = (ln.color_label or ln.color_code or '').strip()
        if color and color not in row.color_labels:
            row.color_labels.append(color)
    if by_size:
        # Thứ tự size gần Excel: S M L XL 2XL …
        order = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL']
        rank = {s: i for i, s in enumerate(order)}

        def _key(r: SizePlanRow):
            return (rank.get(r.size_label.upper(), 100), r.size_label)

        return sorted(by_size.values(), key=_key)

    # Fallback: một hàng tổng theo header.qty
    qty = _q(mo.qty)
    if qty > 0:
        return [SizePlanRow(size_label='Tổng', qty=qty)]
    return []


def build_progress_sheet(
    mo: SxProductionOrder,
    *,
    group_key: str | None = None,
) -> ProgressSheet:
    all_steps = progress_steps()
    all_groups = progress_groups_with_steps()
    gk = (group_key or '').strip().upper()
    if gk:
        groups = [(g, steps) for g, steps in all_groups if g.key == gk]
        steps = [s for s in all_steps if s.group == gk]
    else:
        groups = all_groups
        steps = all_steps
    sizes = _size_plans(mo)
    label_map = {s.label.casefold(): s for s in all_steps}

    stats = list(
        SxProductionStat.objects.filter(
            production_order=mo,
            is_demo=False,
            status=SxProductionStat.STATUS_CONFIRMED,
        ).only('stat_date', 'process_name', 'size_label', 'qty_good')
    )

    # done[(size, key)] 
    done_map: dict[tuple[str, str], Decimal] = {}
    daily_acc: dict[date, dict[tuple[str, str], Decimal]] = {}

    size_set = {r.size_label for r in sizes}
    single_total = len(sizes) == 1 and sizes[0].size_label == 'Tổng'

    for st in stats:
        step = label_map.get((st.process_name or '').strip().casefold())
        if not step:
            continue
        size = (st.size_label or '').strip()
        if single_total:
            size = 'Tổng'
        elif not size:
            continue
        elif size not in size_set and size_set:
            # size trên TKSX không có trong plan — vẫn hiện nếu khớp key
            pass
        qty = _q(st.qty_good)
        if qty <= 0:
            continue
        key = (size, step.key)
        done_map[key] = done_map.get(key, Decimal('0')) + qty
        d = st.stat_date
        if d:
            bucket = daily_acc.setdefault(d, {})
            bucket[key] = bucket.get(key, Decimal('0')) + qty

    matrix: dict[str, dict[str, SheetCell]] = {}
    for row in sizes:
        cells: dict[str, SheetCell] = {}
        for step in steps:
            done = done_map.get((row.size_label, step.key), Decimal('0'))
            rem = row.qty - done
            if rem < 0:
                rem = Decimal('0')
            cells[step.key] = SheetCell(
                process_key=step.key,
                process_label=step.label,
                done=done,
                remaining=rem,
            )
        matrix[row.size_label] = cells

    daily_rows: list[DailyRow] = []
    for d in sorted(daily_acc.keys()):
        daily_rows.append(DailyRow(stat_date=d, cells=daily_acc[d]))

    so = getattr(mo, 'sales_order', None)
    colors: list[str] = []
    for r in sizes:
        for c in r.color_labels:
            if c not in colors:
                colors.append(c)

    done_rows: list[dict] = []
    remain_rows: list[dict] = []
    for row in sizes:
        cells = matrix.get(row.size_label, {})
        done_vals = [cells[s.key].done if s.key in cells else Decimal('0') for s in steps]
        rem_vals = [cells[s.key].remaining if s.key in cells else row.qty for s in steps]
        done_rows.append({'size_label': row.size_label, 'qty': row.qty, 'values': done_vals})
        remain_rows.append({'size_label': row.size_label, 'qty': row.qty, 'values': rem_vals})

    daily_display: list[dict] = []
    for dr in daily_rows:
        # Một hàng ngày × mỗi size (giống Excel: nhiều dòng ngày)
        for row in sizes:
            vals = [
                dr.cells.get((row.size_label, s.key), Decimal('0'))
                for s in steps
            ]
            if any(v > 0 for v in vals):
                daily_display.append({
                    'stat_date': dr.stat_date,
                    'size_label': row.size_label,
                    'values': vals,
                })

    return ProgressSheet(
        mo=mo,
        order_code=(so.code if so else '') or '',
        product_code=mo.product_code or '',
        product_name=mo.product_name or '',
        total_qty=_q(mo.qty) or sum((r.qty for r in sizes), Decimal('0')),
        color_summary=', '.join(colors) if colors else '',
        sizes=sizes,
        groups=groups,
        matrix=matrix,
        daily_rows=daily_rows,
        size_totals_done={},
        done_rows=done_rows,
        remain_rows=remain_rows,
        daily_display=daily_display,
    )


@transaction.atomic
def record_progress_qty(
    *,
    mo_id: int,
    process_key: str,
    size_label: str,
    qty: Decimal,
    stat_date: date | None = None,
    user=None,
) -> SxProductionStat:
    """Ghi SL đạt vào phiếu (TKSX confirmed) — dùng bởi planner trên màn tiến độ."""
    from san_xuat.services.dispatch import _code, _recompute_mo_progress
    from san_xuat.services.sku_catalog import SkuError, resolve_sku_fields

    step = step_by_key(process_key)
    if not step:
        raise PlanningError('Công đoạn không thuộc mẫu cố định.')
    qty = _q(qty)
    if qty <= 0:
        raise PlanningError('SL phải lớn hơn 0.')

    mo = SxProductionOrder.objects.select_for_update().get(pk=mo_id, is_demo=False)
    # Không select_related(sales_order) cùng FOR UPDATE (PG outer join)
    if mo.status == SxProductionOrder.STATUS_CANCELLED:
        raise PlanningError('Lệnh sản xuất đã hủy.')
    if mo.status == SxProductionOrder.STATUS_DRAFT:
        raise PlanningError('Lệnh sản xuất còn nháp — phát hành trước khi ghi tiến độ.')

    size = (size_label or '').strip()
    if size == 'Tổng':
        size = ''

    wc_map = work_center_map()
    wc = wc_map.get(step.work_center_code)
    team = ''
    if wc:
        team = (wc.team_label or wc.name or wc.code or '').strip()

    color_code = ''
    color_label = ''
    if size:
        ln = (
            SxProductionOrderLine.objects.filter(
                production_order=mo,
                size_label__iexact=size,
            )
            .order_by('id')
            .first()
        )
        if ln:
            color_code = ln.color_code or ''
            color_label = ln.color_label or ''

    try:
        resolved = resolve_sku_fields(
            style_code=mo.product_code,
            style_name=mo.product_name or '',
            sku_code='',
            color_code=color_code,
            color_label=color_label,
            size_label=size,
            user=user,
            create_if_missing=bool(size),
        )
    except SkuError:
        resolved = None

    day = stat_date or timezone.localdate()
    # Cộng dồn cùng ngày/CD/size nếu đã có draft hoặc confirmed cùng khóa — tạo phiếu mới rồi confirm
    stat = SxProductionStat.objects.create(
        code=_code('stat', SxProductionStat),
        production_order=mo,
        stat_date=day,
        process_name=step.label,
        qty_good=qty,
        qty_defect=Decimal('0'),
        team_label=team,
        sku=resolved.sku if resolved else None,
        size_label=(resolved.size_label if resolved else size) or '',
        sku_code=(resolved.sku_code if resolved else '') or '',
        color_label=(resolved.color_label if resolved else color_label) or '',
        color_code=(resolved.color_code if resolved else color_code) or '',
        status=SxProductionStat.STATUS_CONFIRMED,
        notes='Từ phiếu tiến độ',
    )
    if mo.status == SxProductionOrder.STATUS_RELEASED:
        mo.status = SxProductionOrder.STATUS_IN_PROGRESS
        mo.save(update_fields=['status'])
    _recompute_mo_progress(mo)
    return stat


def seed_order_plan_steps_from_template(order) -> list:
    """Seed SxSalesOrderPlanStep từ mẫu cố định nếu đơn chưa có bước."""
    from san_xuat.hub_models import SxSalesOrder, SxSalesOrderPlanStep

    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        return []
    existing = list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))
    if existing:
        return existing

    wc_map = work_center_map()
    created: list[SxSalesOrderPlanStep] = []
    for step in progress_steps():
        wc = wc_map.get(step.work_center_code)
        created.append(
            SxSalesOrderPlanStep(
                sales_order=order,
                sequence=step.sequence,
                process_name=step.label,
                work_center_id=wc.pk if wc else None,
                minutes_per_unit=Decimal('0'),
            )
        )
    if created:
        SxSalesOrderPlanStep.objects.bulk_create(created)
    cache = getattr(order, '_prefetched_objects_cache', None)
    if cache is not None:
        cache.pop('plan_steps', None)
    return list(order.plan_steps.select_related('work_center').order_by('sequence', 'id'))
