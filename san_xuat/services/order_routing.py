"""Snapshot routing công đoạn theo dòng đơn đặt hàng.

SoT thực thi (KH / năng lực / LSX) và nhân công GTKH theo đơn: SMV áp dụng trên snapshot đơn.
GT định mức sản phẩm (bảng kỳ) vẫn compute_costing(BOM ProcessStep).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from hrm.menu_permissions import user_can_update_menu
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.hub_models import (
    SxProductionOrder,
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderRoutingLine,
)
from san_xuat.services.ie_ops import VARIANCE_LIMIT_PCT, operation_library_snapshot, resolve_operation
from san_xuat.services.planning import PlanningError


class OrderRoutingError(Exception):
    pass


def _q(value, places: str = '0.0001') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def user_can_edit_order_routing(user) -> bool:
    """IE hoặc Kế hoạch (Sửa) mới được điều SMV / thêm-bớt CĐ trên đơn."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return (
        user_can_update_menu(user, MODULE_SAN_XUAT, 'ie')
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'plan')
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'plan_board')
    )


def assert_order_routing_editable(order: SxSalesOrder) -> None:
    if order.confirm_status != SxSalesOrder.CONFIRM_DRAFT:
        raise OrderRoutingError('Chỉ sửa công đoạn / SMV khi đơn còn nháp.')
    if order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists():
        raise OrderRoutingError('Đơn đã có lệnh sản xuất — không sửa snapshot công đoạn.')


def _copy_from_routing_line(
    order_line: SxSalesOrderLine,
    src,
    *,
    seq_no: int | None = None,
) -> SxSalesOrderRoutingLine:
    return SxSalesOrderRoutingLine(
        sales_order_line=order_line,
        source_routing_line_id=getattr(src, 'pk', None),
        seq_no=int(seq_no if seq_no is not None else src.seq_no or 1),
        operation_id=src.operation_id,
        op_code=(src.op_code or '')[:30],
        op_rev=(src.op_rev or 'R01')[:10],
        op_name_vi=(src.op_name_vi or '')[:200],
        group_code=(src.group_code or '')[:30],
        qty_per_garment=src.qty_per_garment or Decimal('1'),
        library_unit_smv=src.library_unit_smv or Decimal('0'),
        applied_unit_smv=src.applied_unit_smv or Decimal('0'),
        price_factor=src.price_factor or Decimal('0'),
        total_unit_price=src.total_unit_price or Decimal('0'),
        machine_id=src.machine_id,
        machine_code=(src.machine_code or '')[:40],
        work_center_id=src.work_center_id,
        work_center_code=(src.work_center_code or '')[:40],
        skill_level_label=(src.skill_level_label or '')[:60],
        critical_qc=bool(src.critical_qc),
        notes=(src.notes or '')[:255],
        variance_explanation=(src.variance_explanation or '')[:500],
    )


@transaction.atomic
def seed_order_line_routing(
    order_line: SxSalesOrderLine,
    *,
    routing=None,
    replace: bool = True,
) -> int:
    """Copy dòng routing mã hàng → snapshot đơn. replace=True xóa snapshot cũ."""
    routing = routing or order_line.routing
    if replace:
        order_line.routing_lines.all().delete()
    if routing is None:
        return 0
    rows = []
    for src in routing.lines.select_related('operation', 'machine', 'work_center').order_by('seq_no', 'id'):
        row = _copy_from_routing_line(order_line, src)
        row.recompute()
        rows.append(row)
    if rows:
        SxSalesOrderRoutingLine.objects.bulk_create(rows)
    return len(rows)


def seed_order_routing(order: SxSalesOrder) -> int:
    total = 0
    for ln in order.lines.select_related('routing').all():
        total += seed_order_line_routing(ln)
    return total


def steps_dicts_from_order_line(order_line: SxSalesOrderLine) -> list[dict]:
    """Công đoạn LSX từ snapshot đơn (ưu tiên hơn routing mã hàng)."""
    out: list[dict] = []
    lines = order_line.routing_lines.select_related('work_center', 'operation').order_by('seq_no', 'id')
    for i, ln in enumerate(lines):
        name = (ln.op_name_vi or '').strip() or (ln.op_code or '').strip()
        if not name and ln.operation_id:
            name = (getattr(ln.operation, 'name_vi', None) or ln.operation.op_code or '').strip()
        if not name:
            continue
        wc_id = ln.work_center_id
        if not wc_id and (ln.work_center_code or '').strip():
            from san_xuat.hub_models import SxWorkCenter

            wc = SxWorkCenter.objects.filter(
                code__iexact=(ln.work_center_code or '').strip(),
                is_demo=False,
            ).first()
            wc_id = wc.pk if wc else None
        out.append({
            'sequence': ln.seq_no or ((i + 1) * 10),
            'process_name': name,
            'work_center_id': wc_id,
            'manager_id': None,
        })
    return out


def sales_order_line_routing(order_line: SxSalesOrderLine):
    """ProductRouting từ snapshot đơn; fallback routing/BOM mã SP."""
    from san_xuat.services.capacity_from_hrm import map_ie_center_to_hr
    from san_xuat.services.scheduling import ProductRouting, RoutingStep, product_routing

    code = (order_line.product_code or '').strip()
    result = ProductRouting(product_code=code)
    rows: list[RoutingStep] = []
    for line in order_line.routing_lines.select_related('work_center').order_by('seq_no', 'id'):
        minutes = _q(line.total_operation_smv, '0.0001')
        if minutes <= 0:
            continue
        wc = map_ie_center_to_hr(line.work_center) or line.work_center
        rows.append(
            RoutingStep(
                sequence=line.seq_no or 10,
                process_name=line.op_name_vi or line.op_code or '',
                work_center=wc,
                minutes_per_unit=minutes,
            )
        )
    if rows:
        result.steps = rows
        result.source = 'order'
        return result
    return product_routing(code)


def assert_order_ready_to_confirm(order: SxSalesOrder) -> None:
    """Routing bắt buộc trên mọi dòng; SMV > 0; lệch >15% phải giải trình."""
    errors: list[str] = []
    lines = list(order.lines.prefetch_related('routing_lines').all())
    if not lines:
        raise PlanningError('Đơn chưa có dòng sản phẩm.')
    for ln in lines:
        code = ln.product_code or f'#{ln.pk}'
        if not ln.routing_id:
            errors.append(f'{code}: chưa chọn phiên bản công đoạn (routing).')
            continue
        snaps = list(ln.routing_lines.all())
        if not snaps:
            errors.append(f'{code}: routing chưa có công đoạn — IE/KH cần thêm hoặc lấy lại từ mã hàng.')
            continue
        for s in snaps:
            label = f'{code} {s.op_code or s.seq_no}'
            if (s.applied_unit_smv or Decimal('0')) <= 0:
                errors.append(f'{label}: SMV áp dụng phải > 0.')
            if s.is_high_variance and not (s.variance_explanation or '').strip():
                errors.append(
                    f'{label}: lệch SMV {s.smv_variance_pct}% > {VARIANCE_LIMIT_PCT}% — cần giải trình.'
                )
    if errors:
        raise PlanningError('Không xác nhận được đơn. ' + ' '.join(errors))


def _next_seq(order_line: SxSalesOrderLine) -> int:
    last = order_line.routing_lines.order_by('-seq_no').values_list('seq_no', flat=True).first() or 0
    return int(last) + 1


@transaction.atomic
def upsert_order_routing_line(
    *,
    order_line: SxSalesOrderLine,
    line_pk: int | None = None,
    seq_no: int | None = None,
    op_code: str = '',
    op_rev: str = 'R01',
    op_name_vi: str = '',
    group_code: str = '',
    qty_per_garment: Decimal | None = None,
    applied_unit_smv: Decimal | None = None,
    library_unit_smv: Decimal | None = None,
    machine_code: str = '',
    work_center_code: str = '',
    skill_level_label: str = '',
    price_factor: Decimal | None = None,
    total_unit_price: Decimal | None = None,
    variance_explanation: str = '',
    notes: str = '',
    critical_qc: bool | None = None,
) -> SxSalesOrderRoutingLine:
    order = order_line.order
    assert_order_routing_editable(order)

    op_code = (op_code or '').strip().upper()
    if not op_code:
        raise OrderRoutingError('Nhập mã công đoạn.')
    op = resolve_operation(op_code, (op_rev or '').strip() or None)
    snap = operation_library_snapshot(op)
    if not (op_rev or '').strip():
        op_rev = snap.get('op_rev') or (op.op_rev if op else 'R01') or 'R01'
    name = (op_name_vi or '').strip() or snap.get('name_vi', '') or (op.name_vi if op else '')
    if not name:
        raise OrderRoutingError('Nhập tên công đoạn.')
    if not (group_code or '').strip():
        group_code = snap.get('group_code', '')
    if not (machine_code or '').strip():
        machine_code = snap.get('machine_code', '')

    qty = qty_per_garment if qty_per_garment is not None else Decimal('1')
    library = library_unit_smv
    if library is None:
        library = snap.get('library_smv') if snap else Decimal('0')
    if library is None:
        library = Decimal('0')
    applied = applied_unit_smv if applied_unit_smv is not None else Decimal('0')
    if applied <= 0 and library > 0:
        applied = library
    if qty < 0 or applied < 0 or library < 0:
        raise OrderRoutingError('SL/SMV không được âm.')

    from san_xuat.ie_models import SxMachine, normalize_skill_level_label
    from san_xuat.services.capacity_from_hrm import resolve_work_center_code
    from san_xuat.services.process_catalog import ensure_process_name

    machine = SxMachine.objects.filter(code=(machine_code or '').strip()).first() if machine_code else None
    wc_code_raw = (work_center_code or '').strip() or snap.get('work_center_code', '')
    wc = resolve_work_center_code(wc_code_raw, name_hint=f'{group_code} {name}') if wc_code_raw else None

    line = None
    if line_pk:
        line = order_line.routing_lines.filter(pk=line_pk).first()
        if line is None:
            raise OrderRoutingError('Không tìm thấy dòng công đoạn trên đơn.')
    if seq_no is None:
        seq_no = line.seq_no if line else _next_seq(order_line)
    else:
        seq_no = int(seq_no)
        conflict = order_line.routing_lines.filter(seq_no=seq_no)
        if line is not None:
            conflict = conflict.exclude(pk=line.pk)
        if conflict.exists():
            raise OrderRoutingError(f'SEQ {seq_no} đã tồn tại trên dòng đơn này.')

    ensure_process_name(name)
    if line is None:
        line = SxSalesOrderRoutingLine(sales_order_line=order_line)

    skill_val = ''
    if skill_level_label is not None:
        skill_val = normalize_skill_level_label(skill_level_label or '')[:60]
        if not skill_val:
            skill_val = (snap.get('skill_level_label') or '')[:60]
    else:
        skill_val = line.skill_level_label or ''

    line.seq_no = seq_no
    line.operation = op
    line.op_code = op_code[:30]
    line.op_rev = (op_rev or 'R01')[:10]
    line.op_name_vi = name[:200]
    line.group_code = (group_code or '')[:30]
    line.qty_per_garment = qty
    line.library_unit_smv = library
    line.applied_unit_smv = applied
    if price_factor is not None:
        line.price_factor = price_factor
    if total_unit_price is not None:
        line.total_unit_price = total_unit_price
    elif _q(line.price_factor or 0) > 0:
        line.total_unit_price = _q(
            (line.applied_unit_smv or Decimal('0'))
            * (line.qty_per_garment or Decimal('0'))
            * (line.price_factor or Decimal('0')),
            '0.01',
        )
    line.skill_level_label = skill_val
    line.machine = machine
    line.machine_code = (machine_code or (machine.code if machine else '') or '')[:40]
    line.work_center = wc
    line.work_center_code = (wc.code if wc else wc_code_raw)[:40]
    if notes is not None:
        line.notes = (notes or '')[:255]
    if variance_explanation is not None:
        line.variance_explanation = (variance_explanation or '')[:500]
    if critical_qc is not None:
        line.critical_qc = bool(critical_qc)
    line.recompute()
    if line.is_high_variance and not (line.variance_explanation or '').strip():
        # Cho phép lưu nháp; confirm sẽ chặn. Không raise ở đây.
        pass
    line.save()
    return line


@transaction.atomic
def delete_order_routing_line(*, order_line: SxSalesOrderLine, line_pk: int) -> None:
    assert_order_routing_editable(order_line.order)
    line = order_line.routing_lines.filter(pk=line_pk).first()
    if line is None:
        raise OrderRoutingError('Không tìm thấy dòng công đoạn trên đơn.')
    remaining = order_line.routing_lines.exclude(pk=line.pk).count()
    if remaining <= 0:
        raise OrderRoutingError('Phải còn ít nhất một công đoạn trên dòng đơn.')
    line.delete()


@transaction.atomic
def attach_order_line_routing(order_line: SxSalesOrderLine, *, routing_id: int) -> int:
    """Gắn routing mã hàng vào dòng đơn (nháp) rồi seed snapshot."""
    from django.db.models import Q

    from san_xuat.ie_models import SxRouting
    from san_xuat.models import ProductTechDoc

    assert_order_routing_editable(order_line.order)
    try:
        rid = int(routing_id)
    except (TypeError, ValueError):
        raise OrderRoutingError('Chọn phiên bản công đoạn.') from None
    code = (order_line.product_code or '').strip()
    qs = SxRouting.objects.filter(pk=rid)
    if code:
        doc = ProductTechDoc.objects.filter(product_code__iexact=code).only('pk').first()
        q = Q(style_code__iexact=code)
        if doc:
            q |= Q(tech_doc_id=doc.pk)
        qs = qs.filter(q)
    routing = qs.first()
    if routing is None:
        raise OrderRoutingError('Phiên bản công đoạn không tồn tại hoặc không thuộc mã này.')
    order_line.routing = routing
    order_line.save(update_fields=['routing'])
    return seed_order_line_routing(order_line, routing=routing, replace=True)


def routings_for_product(product_code: str):
    from django.db.models import Q

    from san_xuat.ie_models import SxRouting
    from san_xuat.models import ProductTechDoc

    code = (product_code or '').strip()
    if not code:
        return []
    q = Q(style_code__iexact=code)
    doc = ProductTechDoc.objects.filter(product_code__iexact=code).only('pk').first()
    if doc:
        q |= Q(tech_doc_id=doc.pk)
    return list(SxRouting.objects.filter(q).order_by('routing_rev', 'id'))


def default_routing_for_product(product_code: str):
    """Routing mặc định lúc lên đơn: đang áp dụng + đã duyệt, không thì bản active cuối."""
    from san_xuat.ie_models import SxRouting

    rows = routings_for_product(product_code)
    if not rows:
        return None
    approved = [
        r for r in rows
        if r.is_active and r.approval_status == SxRouting.APPROVAL_APPROVED
    ]
    if approved:
        return approved[-1]
    active = [r for r in rows if r.is_active]
    return (active or rows)[-1]


@transaction.atomic
def reset_order_line_routing(order_line: SxSalesOrderLine) -> int:
    assert_order_routing_editable(order_line.order)
    if not order_line.routing_id:
        raise OrderRoutingError('Dòng đơn chưa chọn routing mã hàng.')
    return seed_order_line_routing(order_line, replace=True)
