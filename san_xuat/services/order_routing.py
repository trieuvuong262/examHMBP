"""Snapshot routing công đoạn theo dòng đơn đặt hàng.

SoT thực thi (KH / năng lực / LSX) và nhân công GTKH theo đơn: SMV đơn hàng trên snapshot.
Baseline snapshot ``library_unit_smv`` = SMV sản phẩm từ OB.
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


def _manager_prefetch_cache_name(manager) -> str | None:
    name = getattr(manager, 'prefetch_cache_name', None)
    if name:
        return name
    remote = getattr(getattr(manager, 'field', None), 'remote_field', None)
    return getattr(remote, 'cache_name', None) if remote is not None else None


def _relations_loaded(rows, paths) -> bool:
    for obj in rows:
        for path in paths:
            cur = obj
            for name in path.split('__'):
                if cur is None:
                    break
                try:
                    field = cur._meta.get_field(name)
                except Exception:
                    return False
                if not hasattr(field, 'is_cached') or not field.is_cached(cur):
                    return False
                cur = getattr(cur, name)
    return True


def related_manager_rows(manager, *, select_related=(), order_by=()):
    """Dùng prefetch cache nếu có (và đã nạp đủ ``select_related``); không thì query lại."""
    instance = getattr(manager, 'instance', None)
    cache_name = _manager_prefetch_cache_name(manager)
    cache = getattr(instance, '_prefetched_objects_cache', None) if instance is not None else None
    if (
        cache is not None
        and cache_name
        and cache_name in cache
        and _relations_loaded(cache[cache_name], select_related)
    ):
        rows = list(manager.all())
        if order_by:
            def _sort_key(obj):
                vals = []
                for field in order_by:
                    vals.append(getattr(obj, field, 0) or 0)
                return tuple(vals)

            rows.sort(key=_sort_key)
        return rows
    qs = manager.all()
    if select_related:
        qs = qs.select_related(*select_related)
    if order_by:
        qs = qs.order_by(*order_by)
    return list(qs)


def user_can_edit_order_routing(user) -> bool:
    """IE hoặc Kế hoạch (Sửa) mới được điều SMV / thêm-bớt CĐ trên đơn."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return (
        user_can_update_menu(user, MODULE_SAN_XUAT, 'ie')
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'plan')
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'plan_board')
    )


def order_has_active_mo(order: SxSalesOrder) -> bool:
    return order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).exists()


def _norm_name(value) -> str:
    return ' '.join(str(value or '').split()).casefold()


def _match_mo_step(candidates: list, row: dict):
    """Ghép công đoạn LSX với dòng OB đơn: ưu tiên mã công đoạn, không có thì theo tên."""
    code = (row.get('op_code') or '').strip().upper()
    if code:
        for step in candidates:
            if (step.op_code or '').strip().upper() == code:
                return step
    name = _norm_name(row.get('process_name'))
    if name:
        for step in candidates:
            if (step.op_code or '').strip() and code:
                # Bước đã có mã khác → không ghép theo tên để tránh nhầm.
                continue
            if _norm_name(step.process_name) == name:
                return step
    return None


def _mo_step_has_output(mo, step) -> bool:
    """Công đoạn LSX đã có sản lượng / phân công / đang làm → không được xóa."""
    from san_xuat.hub_models import (
        SxMoProcessStep,
        SxProductionStat,
        SxWipBalance,
        SxWorkAssignment,
    )

    if step.status != SxMoProcessStep.STATUS_PENDING:
        return True
    if step.assignees.exists():
        return True
    name = (step.process_name or '').strip()
    if not name:
        return False
    if SxProductionStat.objects.filter(production_order=mo, process_name__iexact=name).exists():
        return True
    if SxWipBalance.objects.filter(
        production_order=mo, process_name__iexact=name, qty__gt=0,
    ).exists():
        return True
    return SxWorkAssignment.objects.filter(
        production_order=mo, process_name__iexact=name,
    ).exists()


def assert_no_duplicate_product_lines(order_line: SxSalesOrderLine) -> None:
    """Chốt D: đơn có ≥2 dòng cùng mã hàng thì không cho sửa OB."""
    code = (order_line.product_code or '').strip()
    if not code:
        return
    if order_line.order.lines.filter(product_code__iexact=code).count() > 1:
        raise OrderRoutingError(
            f'Đơn có nhiều dòng cùng mã {code} — không sửa OB trên đơn được '
            '(LSX không xác định dòng nào).'
        )


@transaction.atomic
def sync_order_plan_steps_from_ob(order: SxSalesOrder) -> int:
    """Chốt B: tính lại lộ trình KHSX theo OB mới (bỏ chỉnh tay), rồi tự tách ngày."""
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        return 0
    if order.plan_status in (
        SxSalesOrder.PLAN_DONE, SxSalesOrder.PLAN_CANCELLED, SxSalesOrder.PLAN_ON_HOLD,
    ):
        return 0
    from san_xuat.services.plan_board import apply_auto_team_day_splits
    from san_xuat.services.plan_route import ensure_order_plan_steps

    order.plan_steps.all().delete()
    cache = getattr(order, '_prefetched_objects_cache', None)
    if cache is not None:
        cache.pop('plan_steps', None)
        cache.pop('lines', None)
    steps = ensure_order_plan_steps(order)
    try:
        apply_auto_team_day_splits(order, replace_existing=True)
    except PlanningError:
        pass
    return len(steps or [])


@transaction.atomic
def sync_active_mos_from_order(order: SxSalesOrder, *, user=None) -> int:
    """Apply the order OB snapshot to active MOs without resetting production history."""
    from san_xuat.hub_models import SxMoProcessStep
    from san_xuat.services.plan_audit import log_plan_action

    changed = 0
    for mo in order.production_orders.select_for_update().filter(is_demo=False).exclude(
        status__in=(SxProductionOrder.STATUS_CANCELLED, SxProductionOrder.STATUS_DONE),
    ):
        line = order.lines.filter(product_code=mo.product_code).prefetch_related(
            'routing_lines',
        ).first()
        if line is None:
            continue
        source_rows = steps_dicts_from_order_line(line)
        all_steps = list(mo.mo_process_steps.all())
        used_seqs = {int(s.sequence) for s in all_steps}
        unmatched = list(all_steps)
        before = []
        after = []
        for row in source_rows:
            step = _match_mo_step(unmatched, row)
            if step is None:
                seq = int(row.get('sequence') or 0) or (max(used_seqs or {0}) + 10)
                while seq in used_seqs:
                    seq += 1
                used_seqs.add(seq)
                SxMoProcessStep.objects.create(
                    production_order=mo,
                    sequence=seq,
                    process_name=(row.get('process_name') or '')[:120],
                    op_code=(row.get('op_code') or '')[:30],
                    work_center_id=row.get('work_center_id'),
                    count_minutes=row.get('count_minutes') or 0,
                    transfer_minutes=row.get('transfer_minutes') or 0,
                    applied_unit_smv=row.get('applied_unit_smv') or 0,
                )
                after.append({
                    'sequence': seq,
                    'process_name': row.get('process_name') or '',
                    'applied_unit_smv': str(row.get('applied_unit_smv') or 0),
                    'action': 'add',
                })
                changed += 1
                continue
            unmatched.remove(step)
            before.append({
                'sequence': step.sequence,
                'process_name': step.process_name,
                'applied_unit_smv': str(step.applied_unit_smv or 0),
            })
            fields = []
            step.process_name = (row.get('process_name') or step.process_name or '')[:120]
            step.work_center_id = row.get('work_center_id')
            step.count_minutes = row.get('count_minutes') or 0
            step.transfer_minutes = row.get('transfer_minutes') or 0
            step.op_code = (row.get('op_code') or step.op_code or '')[:30]
            step.removed_from_ob = False
            fields = [
                'process_name', 'work_center_id', 'count_minutes', 'transfer_minutes',
                'op_code', 'removed_from_ob',
            ]
            if step.status != SxMoProcessStep.STATUS_DONE:
                step.applied_unit_smv = row.get('applied_unit_smv') or 0
                fields.append('applied_unit_smv')
            step.save(update_fields=fields)
            after.append({
                'sequence': step.sequence,
                'process_name': step.process_name,
                'applied_unit_smv': str(step.applied_unit_smv or 0),
            })
            changed += 1
        # Công đoạn LSX không còn trên OB đơn
        for step in unmatched:
            if step.removed_from_ob:
                continue
            info = {
                'sequence': step.sequence,
                'process_name': step.process_name,
                'applied_unit_smv': str(step.applied_unit_smv or 0),
            }
            before.append(info)
            if _mo_step_has_output(mo, step):
                step.removed_from_ob = True
                step.save(update_fields=['removed_from_ob'])
                after.append({**info, 'action': 'flag_removed'})
            else:
                step.delete()
                after.append({**info, 'action': 'delete'})
            changed += 1
        if before or after:
            log_plan_action(
                action='update', obj=mo,
                summary=f'Cập nhật snapshot OB phần còn lại từ đơn {order.code}.',
                changes={'before': before, 'after': after, 'order_id': order.pk}, user=user,
            )
    return changed


def order_tech_is_editable(order: SxSalesOrder) -> bool:
    """Cho sửa kỹ thuật khi đơn chưa hủy/hoàn thành; LSX nhận thay đổi cho phần còn lại."""
    return order.plan_status not in {
        SxSalesOrder.PLAN_DONE,
        SxSalesOrder.PLAN_CANCELLED,
    }


def assert_order_routing_editable(order: SxSalesOrder) -> None:
    if not order_tech_is_editable(order):
        raise OrderRoutingError('Đơn đã hoàn thành hoặc hủy — không sửa snapshot BOM/OB.')


def _ob_smv_seconds(src) -> tuple[Decimal, Decimal]:
    """SMV thư viện + SMV sản phẩm (giây) từ dòng OB hồ sơ thiết kế."""
    library = _q(getattr(src, 'library_unit_smv', 0) or 0)
    product = _q(getattr(src, 'applied_unit_smv', 0) or 0)
    if product <= 0:
        product = library
    return library, product


def _fold_op(code: str) -> str:
    return (code or '').strip().casefold()


def _next_unique_seq(raw, used: set[int], index: int) -> int:
    """SEQ ổn định: giữ số gốc nếu hợp lệ, không thì 10/20/30… không trùng."""
    try:
        seq = int(raw or 0)
    except (TypeError, ValueError):
        seq = 0
    if seq <= 0 or seq in used:
        seq = (index + 1) * 10
        while seq <= 0 or seq in used:
            seq += 10
    used.add(seq)
    return seq


def _smv_pct_of(line) -> Decimal:
    std = line.library_unit_smv or Decimal('0')
    applied = line.applied_unit_smv or Decimal('0')
    if std > 0:
        return (applied / std * Decimal('100')).quantize(Decimal('0.01'))
    return Decimal('100')


def smv_override_dicts(order_line: SxSalesOrderLine) -> list[dict]:
    """Snapshot SMV đơn hàng (kèm mã CĐ) để hydrate form / áp lại khi đổi BOM-OB."""
    out: list[dict] = []
    for rl in order_line.routing_lines.order_by('seq_no', 'id'):
        applied = rl.applied_unit_smv or Decimal('0')
        out.append({
            'seq': rl.seq_no,
            'op_code': rl.op_code or '',
            'smv': float(applied),
            'smv_pct': float(_smv_pct_of(rl)),
            'smv_mode': 'pct',
            'notes': rl.notes or '',
        })
    return out


def _match_routing_line(lines, *, seq: int, op_code: str, used: set[int]):
    """Khớp override theo mã CĐ (ổn định); seq chỉ dùng khi không có mã — tránh gán nhầm khi đổi OB."""
    code = _fold_op(op_code)
    unused = [ln for ln in lines if ln.pk not in used]
    if code and seq:
        for ln in unused:
            if _fold_op(ln.op_code) == code and ln.seq_no == seq:
                return ln
    if code:
        for ln in unused:
            if _fold_op(ln.op_code) == code:
                return ln
    if seq and not code:
        for ln in unused:
            if ln.seq_no == seq:
                return ln
    return None


def _copy_from_routing_line(
    order_line: SxSalesOrderLine,
    src,
    *,
    seq_no: int | None = None,
) -> SxSalesOrderRoutingLine:
    # Baseline trên đơn = SMV sản phẩm (OB applied, fallback thư viện).
    _library, product = _ob_smv_seconds(src)
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
        library_unit_smv=product,
        applied_unit_smv=product,
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
        count_minutes=getattr(src, 'count_minutes', Decimal('0')) or Decimal('0'),
        transfer_minutes=getattr(src, 'transfer_minutes', Decimal('0')) or Decimal('0'),
    )


def smv_from_process_step(step) -> Decimal:
    """SMV phút/cái từ BOM ProcessStep (chuẩn giờ, không thì 60/định mức giờ)."""
    smv = _q(getattr(step, 'std_time_minutes', 0))
    if smv > 0:
        return smv
    norm = _q(getattr(step, 'norm_per_hour', 0))
    if norm > 0:
        return _q(Decimal('60') / norm)
    return Decimal('0')


def _step_code_and_name(*, code='', name='', operation=None) -> tuple[str, str]:
    """Mã + tên công đoạn; thiếu tên thì lấy từ thư viện IE."""
    code = (code or '').strip()
    name = (name or '').strip()
    if operation is not None:
        if not code:
            code = (getattr(operation, 'op_code', None) or '').strip()
        op_name = (getattr(operation, 'name_vi', None) or '').strip()
        if op_name and (not name or name.upper() == code.upper()):
            name = op_name
    return code, name


def process_preview_from_routing(routing, *, limit: int = 80) -> list[dict]:
    out = []
    if routing is None:
        return out
    used: set[int] = set()
    for i, src in enumerate(routing.lines.select_related('operation').order_by('seq_no', 'id')[:limit]):
        library, product = _ob_smv_seconds(src)
        code, name = _step_code_and_name(
            code=src.op_code,
            name=src.op_name_vi,
            operation=getattr(src, 'operation', None),
        )
        out.append({
            'seq': _next_unique_seq(src.seq_no, used, i),
            'code': code,
            'name': name,
            'smv_library': str(library),
            'smv_product': str(product),
            'smv_std': str(product),
            'smv': str(product),
            'notes': (src.notes or '')[:255],
            'source': 'ie',
        })
    return out


def process_preview_from_bom(bom, *, limit: int = 80) -> list[dict]:
    out = []
    if bom is None:
        return out
    steps = bom.process_steps
    if hasattr(steps, 'select_related'):
        steps = steps.select_related('operation', 'routing_line')
    used: set[int] = set()
    for i, src in enumerate(steps.order_by('sequence', 'id')[:limit]):
        rl = getattr(src, 'routing_line', None)
        if rl is not None:
            library, product = _ob_smv_seconds(rl)
        else:
            library = product = Decimal('0')
        smv = product if product > 0 else _q(smv_from_process_step(src) * Decimal('60'))
        if product <= 0:
            product = smv
        if library <= 0:
            library = smv
        code, name = _step_code_and_name(
            code=src.op_code,
            name=src.process_name,
            operation=getattr(src, 'operation', None),
        )
        out.append({
            'seq': _next_unique_seq(src.sequence, used, i),
            'code': code,
            'name': name,
            'smv_library': str(library),
            'smv_product': str(product),
            'smv_std': str(smv),
            'smv': str(smv),
            'notes': (getattr(src, 'notes', None) or '')[:255],
            'source': 'bom',
        })
    return out


def _copy_from_process_step(order_line: SxSalesOrderLine, src) -> SxSalesOrderRoutingLine:
    # Ưu tiên SMV sản phẩm trên dòng OB gắn ProcessStep; không thì phút BOM → giây.
    rl = getattr(src, 'routing_line', None)
    smv = _ob_smv_seconds(rl)[1] if rl is not None else Decimal('0')
    if smv <= 0:
        smv = _q(smv_from_process_step(src) * Decimal('60'))
    wc = getattr(src, 'work_center', None)
    return SxSalesOrderRoutingLine(
        sales_order_line=order_line,
        seq_no=int(src.sequence or 0) or 10,
        operation=getattr(src, 'operation', None),
        op_code=(getattr(src, 'op_code', None) or '')[:30],
        op_rev='R01',
        op_name_vi=(src.process_name or '')[:200],
        library_unit_smv=smv,
        applied_unit_smv=smv,
        qty_per_garment=Decimal('1'),
        work_center=wc,
        work_center_code=(wc.code if wc else '')[:40],
        count_minutes=getattr(src, 'count_minutes', Decimal('0')) or Decimal('0'),
        transfer_minutes=getattr(src, 'transfer_minutes', Decimal('0')) or Decimal('0'),
        notes=(getattr(src, 'notes', None) or '')[:255],
    )


def apply_smv_overrides(order_line: SxSalesOrderLine, overrides) -> int:
    """Ghi đè SMV đơn hàng theo mã CĐ (rồi seq) — không đụng SMV sản phẩm baseline."""
    if not overrides:
        return 0
    parsed: list[tuple[int, str, Decimal, str, str | None, Decimal | None]] = []
    for row in overrides:
        if not isinstance(row, dict):
            continue
        try:
            seq = int(row.get('seq') or 0)
            smv = _q(row.get('smv') or 0)
        except (TypeError, ValueError):
            continue
        op_code = str(row.get('op_code') or row.get('code') or '').strip()
        if seq <= 0 and not op_code:
            continue
        expl = str(row.get('explanation') or row.get('reason') or '').strip()[:500]
        notes = None
        if 'notes' in row or 'description' in row:
            notes = str(row.get('notes') or row.get('description') or '').strip()[:255]
        pct = None
        mode = str(row.get('smv_mode') or '').strip().lower()
        if mode != 'qty' and row.get('smv_pct') is not None and str(row.get('smv_pct')).strip() != '':
            try:
                pct = _q(row.get('smv_pct'))
            except (TypeError, ValueError):
                pct = None
        parsed.append((seq, op_code, smv, expl, notes, pct))
    n = 0
    lines = list(order_line.routing_lines.all())
    used: set[int] = set()
    for seq, op_code, smv, expl, notes, pct in parsed:
        line = _match_routing_line(lines, seq=seq, op_code=op_code, used=used)
        if line is None:
            continue
        used.add(line.pk)
        if pct is not None:
            std = line.library_unit_smv or Decimal('0')
            smv = (std * pct / Decimal('100')).quantize(Decimal('0.0001'))
        line.applied_unit_smv = smv
        line.recompute()
        fields = ['applied_unit_smv', 'total_operation_smv', 'smv_variance_pct']
        if expl:
            line.variance_explanation = expl
            fields.append('variance_explanation')
        if notes is not None:
            line.notes = notes
            fields.append('notes')
        line.save(update_fields=fields)
        n += 1
    return n


def scale_order_line_applied_smv(
    order_line: SxSalesOrderLine,
    pct,
    explanation: str = '',
) -> int:
    """Nhân SMV đơn hàng cả dòng theo % lệch so với SMV sản phẩm (baseline trên đơn)."""
    assert_order_routing_editable(order_line.order)
    factor = Decimal('1') + _q(pct, '0.01') / Decimal('100')
    if factor <= 0:
        raise OrderRoutingError('% lệch không hợp lệ — SMV đơn hàng phải > 0.')
    expl = (explanation or '').strip()[:500]
    n = 0
    for line in order_line.routing_lines.all():
        std = line.library_unit_smv or Decimal('0')
        line.applied_unit_smv = _q(std * factor)
        line.recompute()
        fields = ['applied_unit_smv', 'total_operation_smv', 'smv_variance_pct']
        if expl and line.is_high_variance:
            line.variance_explanation = expl
            fields.append('variance_explanation')
        line.save(update_fields=fields)
        n += 1
    if not n:
        raise OrderRoutingError('Dòng đơn chưa có công đoạn để áp SMV.')
    return n


@transaction.atomic
def seed_order_line_routing(
    order_line: SxSalesOrderLine,
    *,
    routing=None,
    replace: bool = True,
) -> int:
    """Copy routing IE, không có thì lấy công đoạn BOM → snapshot đơn."""
    routing = routing or order_line.routing
    if replace:
        order_line.routing_lines.all().delete()
    rows = []
    if routing is not None:
        used_seq: set[int] = set()
        for i, src in enumerate(
            routing.lines.select_related('operation', 'machine', 'work_center').order_by('seq_no', 'id')
        ):
            row = _copy_from_routing_line(order_line, src)
            row.seq_no = _next_unique_seq(row.seq_no, used_seq, i)
            row.recompute()
            rows.append(row)
    elif order_line.bom_version_id:
        bom = order_line.bom_version
        if bom is None:
            from san_xuat.models import BomVersion

            bom = BomVersion.objects.filter(pk=order_line.bom_version_id).first()
        if bom is not None:
            used_seq: set[int] = set()
            for i, src in enumerate(
                bom.process_steps.select_related(
                    'operation', 'work_center', 'routing_line',
                ).order_by('sequence', 'id')
            ):
                row = _copy_from_process_step(order_line, src)
                row.seq_no = _next_unique_seq(row.seq_no, used_seq, i)
                row.recompute()
                rows.append(row)
    if rows:
        SxSalesOrderRoutingLine.objects.bulk_create(rows)
    return len(rows)


def seed_order_routing(order: SxSalesOrder) -> int:
    total = 0
    for ln in order.lines.select_related('routing', 'bom_version').all():
        total += seed_order_line_routing(ln)
    return total


def steps_dicts_from_order_line(order_line: SxSalesOrderLine) -> list[dict]:
    """Công đoạn LSX từ snapshot đơn (ưu tiên hơn routing mã hàng)."""
    out: list[dict] = []
    lines = related_manager_rows(
        order_line.routing_lines,
        select_related=('work_center', 'operation'),
        order_by=('seq_no', 'id'),
    )
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
            'applied_unit_smv': ln.applied_unit_smv or Decimal('0'),
            'count_minutes': ln.count_minutes or Decimal('0'),
            'transfer_minutes': ln.transfer_minutes or Decimal('0'),
            'op_code': (ln.op_code or '').strip().upper(),
        })
    return out


def sales_order_line_routing(order_line: SxSalesOrderLine):
    """ProductRouting từ snapshot đơn; fallback routing/BOM mã SP."""
    from san_xuat.services.capacity_from_hrm import map_ie_center_to_hr
    from san_xuat.services.scheduling import ProductRouting, RoutingStep, product_routing

    code = (order_line.product_code or '').strip()
    result = ProductRouting(product_code=code)
    rows: list[RoutingStep] = []
    src_lines = related_manager_rows(
        order_line.routing_lines,
        select_related=('work_center', 'operation__group'),
        order_by=('seq_no', 'id'),
    )
    for line in src_lines:
        # Snapshot đơn lưu SMV giây → phút cho lịch/công suất.
        minutes = _q((line.total_operation_smv or Decimal('0')) / Decimal('60'), '0.0001')
        if minutes <= 0:
            continue
        wc = map_ie_center_to_hr(line.work_center) or line.work_center
        group_code = (line.group_code or '').strip()
        if not group_code and line.operation_id and line.operation and line.operation.group_id:
            group_code = (line.operation.group.code or '').strip()
        rows.append(
            RoutingStep(
                sequence=line.seq_no or 10,
                process_name=line.op_name_vi or line.op_code or '',
                work_center=wc,
                minutes_per_unit=minutes,
                count_minutes=_q(getattr(line, 'count_minutes', 0)),
                transfer_minutes=_q(getattr(line, 'transfer_minutes', 0)),
                group_code=group_code,
                board_slug=(getattr(line, 'board_slug', '') or '').strip().lower(),
            )
        )
    if rows:
        result.steps = rows
        result.source = 'order'
        return result
    return product_routing(code)


def assert_order_ready_to_confirm(order: SxSalesOrder) -> None:
    """BOM/OB không bắt buộc lúc xác nhận — bắt buộc khi Chuyển SX trên KHSX.

    Nếu dòng đã có snapshot công đoạn thì SMV đơn hàng từng CĐ phải > 0.
    """
    errors: list[str] = []
    lines = list(order.lines.prefetch_related('routing_lines').all())
    if not lines:
        raise PlanningError('Đơn chưa có dòng sản phẩm.')
    for ln in lines:
        code = ln.product_code or f'#{ln.pk}'
        for s in ln.routing_lines.all():
            if (s.applied_unit_smv or Decimal('0')) <= 0:
                label = f'{code} {s.op_code or s.seq_no}'
                errors.append(f'{label}: SMV đơn hàng phải > 0.')
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
    count_minutes: Decimal | None = None,
    transfer_minutes: Decimal | None = None,
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
        # Hệ số đơn giá = VNĐ/phút; SMV lưu giây.
        line.total_unit_price = _q(
            ((line.applied_unit_smv or Decimal('0')) / Decimal('60'))
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
    if count_minutes is not None:
        line.count_minutes = max(_q(count_minutes, '0.01'), Decimal('0'))
    if transfer_minutes is not None:
        line.transfer_minutes = max(_q(transfer_minutes, '0.01'), Decimal('0'))
    line.recompute()
    if line.is_high_variance and not (line.variance_explanation or '').strip():
        # Cho phép lưu nháp; confirm sẽ chặn. Không raise ở đây.
        pass
    line.save()
    return line


@transaction.atomic
def apply_order_routing_edits(
    order_line: SxSalesOrderLine,
    *,
    updates: list | None = None,
    adds: list | None = None,
    deletes: list | None = None,
    user=None,
) -> dict:
    """Lưu OB trên đơn theo lô: sửa SMV đơn hàng, thêm công đoạn, xóa công đoạn."""
    assert_order_routing_editable(order_line.order)
    stats = {'updated': 0, 'added': 0, 'deleted': 0}
    from san_xuat.services.order_history import ob_snapshot

    stats['_before'] = ob_snapshot(order_line)

    for raw in updates or []:
        if not isinstance(raw, dict):
            continue
        try:
            pk = int(raw.get('pk') or 0)
            smv = _q(raw.get('applied_unit_smv'))
        except Exception:
            raise OrderRoutingError('SMV đơn hàng không hợp lệ.') from None
        if smv < 0:
            raise OrderRoutingError('SMV đơn hàng không được âm.')
        line = order_line.routing_lines.filter(pk=pk).first() if pk else None
        if line is None:
            raise OrderRoutingError('Không tìm thấy dòng công đoạn trên đơn.')
        if line.applied_unit_smv == smv:
            continue
        line.applied_unit_smv = smv
        line.recompute()
        line.save()
        stats['updated'] += 1

    for raw in adds or []:
        if not isinstance(raw, dict):
            continue
        smv_raw = raw.get('applied_unit_smv')
        upsert_order_routing_line(
            order_line=order_line,
            op_code=str(raw.get('op_code') or ''),
            op_rev=str(raw.get('op_rev') or ''),
            applied_unit_smv=_q(smv_raw) if smv_raw not in (None, '') else None,
        )
        stats['added'] += 1

    delete_ids = set()
    for raw in deletes or []:
        try:
            delete_ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    if delete_ids:
        if not order_line.routing_lines.exclude(pk__in=delete_ids).exists():
            raise OrderRoutingError('Phải còn ít nhất một công đoạn trên dòng đơn.')
        stats['deleted'] = order_line.routing_lines.filter(pk__in=delete_ids).delete()[0]
    before = stats.pop('_before')
    if stats['updated'] or stats['added'] or stats['deleted']:
        log_order_ob_change(
            order_line, before=before,
            summary=(
                f"Sửa OB trên đơn — {order_line.product_name or order_line.product_code}: "
                f"sửa {stats['updated']}, thêm {stats['added']}, xóa {stats['deleted']} CĐ"
            ),
            user=user,
        )
    return stats


def log_order_ob_change(order_line: SxSalesOrderLine, *, before: list, summary: str, source: str = '', user=None) -> None:
    """Ghi nhật ký OB trên đơn (trước / sau) — user lấy từ thread-local request nếu không truyền."""
    from san_xuat.services.order_history import log_order_event, ob_snapshot

    log_order_event(
        order=order_line.order,
        action='update',
        kind='ob',
        summary=summary,
        user=user,
        line_id=order_line.pk,
        product=f'{order_line.product_code} — {order_line.product_name}'.strip(' —'),
        before=before,
        after=ob_snapshot(order_line),
        source=source,
    )


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
def update_order_line_bom_overrides(
    order_line: SxSalesOrderLine,
    *,
    rows: list[dict],
    user=None,
) -> int:
    """Lưu snapshot BOM trên đơn, cho phép chỉnh khi LSX chạy."""
    from san_xuat.services.sales_orders import _normalize_bom_overrides
    from san_xuat.services.plan_audit import log_plan_action

    assert_order_routing_editable(order_line.order)
    before = list(order_line.bom_line_overrides or [])
    normalized = _normalize_bom_overrides(rows)
    if not normalized:
        raise OrderRoutingError('BOM phải còn ít nhất một dòng NPL hợp lệ.')
    order_line.bom_line_overrides = normalized
    order_line.save(update_fields=['bom_line_overrides'])
    log_plan_action(
        action='update', obj=order_line.order,
        summary=f'Sửa BOM trên đơn — {order_line.product_name or order_line.product_code}',
        changes={
            'kind': 'bom',
            'line_id': order_line.pk,
            'product': f'{order_line.product_code} — {order_line.product_name}'.strip(' —'),
            'before': before,
            'after': normalized,
            'npl_deferred': order_npl_deferred(order_line.order),
        },
        user=user,
    )
    order = order_line.order
    # Chốt A: đơn nháp / tạm giữ chỉ lưu BOM; NPL KHSX tính khi xác nhận / bỏ giữ.
    if (
        order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED
        and order.plan_status != SxSalesOrder.PLAN_ON_HOLD
    ):
        from san_xuat.services.plan_order_npl import sync_order_npl
        try:
            sync_order_npl(order_id=order_line.order_id, apply_schedule=True)
        except PlanningError as exc:
            raise OrderRoutingError(str(exc)) from exc
    return len(normalized)


def order_npl_deferred(order: SxSalesOrder) -> bool:
    """True = lưu BOM nhưng chưa tính NPL KHSX (đơn nháp / tạm giữ)."""
    return (
        order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED
        or order.plan_status == SxSalesOrder.PLAN_ON_HOLD
    )


def boms_for_product(product_code: str):
    from san_xuat.services.products import find_tech_doc_for_code

    code = (product_code or '').strip()
    if not code:
        return []
    doc = find_tech_doc_for_code(code)
    if doc is None:
        return []
    return list(doc.bom_versions.order_by('created_at', 'id'))


@transaction.atomic
def attach_order_line_bom(order_line: SxSalesOrderLine, *, bom_version_id: int) -> int:
    """Gắn phiên bản BOM vào dòng đơn (nháp / chờ xếp KHSX)."""
    from san_xuat.models import BomVersion
    from san_xuat.services.sales_orders import bom_lines_snapshot, merge_bom_overrides

    assert_order_routing_editable(order_line.order)
    try:
        bid = int(bom_version_id)
    except (TypeError, ValueError):
        raise OrderRoutingError('Chọn phiên bản BOM.') from None
    bom = BomVersion.objects.filter(pk=bid).select_related('tech_doc').first()
    if bom is None:
        raise OrderRoutingError('Phiên bản BOM không tồn tại.')
    code = (order_line.product_code or '').strip().casefold()
    bom_code = ((getattr(bom.tech_doc, 'product_code', None) or '').strip().casefold())
    if code and bom_code and code != bom_code:
        raise OrderRoutingError('Phiên bản BOM không thuộc mã sản phẩm này.')
    order_line.bom_version = bom
    fresh = bom_lines_snapshot(bom.pk)
    prev = list(order_line.bom_line_overrides or [])
    if prev:
        order_line.bom_line_overrides = merge_bom_overrides(fresh, prev)
    else:
        order_line.bom_line_overrides = fresh
    order_line.save(update_fields=['bom_version', 'bom_line_overrides'])
    if order_line.routing_lines.exists():
        return order_line.routing_lines.count()
    return seed_order_line_routing(order_line, replace=True)


@transaction.atomic
def attach_order_line_routing(order_line: SxSalesOrderLine, *, routing_id: int) -> int:
    """Gắn routing mã hàng vào dòng đơn rồi seed snapshot."""
    from san_xuat.ie_models import SxRouting

    assert_order_routing_editable(order_line.order)
    try:
        rid = int(routing_id)
    except (TypeError, ValueError):
        raise OrderRoutingError('Chọn phiên bản công đoạn.') from None
    code = (order_line.product_code or '').strip()
    qs = SxRouting.objects.filter(pk=rid)
    if code:
        qs = qs.filter(_routing_q_for_product(code))
    routing = qs.first()
    if routing is None:
        raise OrderRoutingError('Phiên bản công đoạn không tồn tại hoặc không thuộc mã này.')
    prev = smv_override_dicts(order_line)
    order_line.routing = routing
    order_line.save(update_fields=['routing'])
    n = seed_order_line_routing(order_line, routing=routing, replace=True)
    if prev:
        apply_smv_overrides(order_line, prev)
    return n


def _routing_q_for_product(product_code: str):
    from django.db.models import Q

    from san_xuat.services.products import find_tech_doc_for_code, product_lookup_codes

    code = (product_code or '').strip()
    q = Q()
    if not code:
        return q
    for item in product_lookup_codes(code):
        q |= Q(style_code__iexact=item)
    doc = find_tech_doc_for_code(code)
    if doc:
        q |= Q(tech_doc_id=doc.pk) | Q(bom_versions__tech_doc_id=doc.pk)
        doc_code = (doc.product_code or '').strip()
        if doc_code:
            q |= Q(style_code__iexact=doc_code)
    return q


def routings_for_product(product_code: str):
    from san_xuat.ie_models import SxRouting

    code = (product_code or '').strip()
    if not code:
        return []
    q = _routing_q_for_product(code)
    if not q:
        return []
    return list(SxRouting.objects.filter(q).distinct().order_by('routing_rev', 'id'))


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
