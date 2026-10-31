"""Cap nhat BOM / OB tu don hang ve ho so thiet ke (tao phien ban moi)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from san_xuat.hub_models import SxSalesOrder, SxSalesOrderLine


class OrderTechPublishError(Exception):
    pass


_Q4 = Decimal('0.0001')
_Q2 = Decimal('0.01')


def _d(value, q=_Q4) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(q, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0').quantize(q)


@dataclass
class PublishLineResult:
    product_code: str
    doc_code: str = ''
    doc_id: int | None = None
    label: str = ''
    n_lines: int = 0
    skipped: list[str] = field(default_factory=list)
    linked_bom: str = ''
    error: str = ''


@dataclass
class PublishResult:
    kind: str
    items: list[PublishLineResult] = field(default_factory=list)

    @property
    def ok_items(self) -> list[PublishLineResult]:
        return [it for it in self.items if not it.error]

    @property
    def failed_items(self) -> list[PublishLineResult]:
        return [it for it in self.items if it.error]


def user_can_publish_order_tech(user) -> bool:
    """Can quyen sua BOM/OB tren don (IE/Ke hoach) va quyen cap nhat module San xuat."""
    from hrm.module_permissions import MODULE_SAN_XUAT, user_can_update_module
    from san_xuat.services.order_routing import user_can_edit_order_routing

    return user_can_edit_order_routing(user) and user_can_update_module(user, MODULE_SAN_XUAT)


def _doc_for_line(order_line: SxSalesOrderLine):
    from san_xuat.services.products import find_tech_doc_for_code

    if order_line.bom_version_id and order_line.bom_version is not None:
        return order_line.bom_version.tech_doc
    routing = order_line.routing
    if routing is not None and routing.tech_doc_id:
        return routing.tech_doc
    return find_tech_doc_for_code(order_line.product_code or '')


def design_qty(row: dict) -> Decimal:
    """Định mức thiết kế của 1 dòng snapshot BOM trên đơn.

    `qty_mode='pct'` = hệ thống phân bổ theo đơn (vd. nhãn size theo cơ cấu size: S 0%, M 25%…)
    → không phải sửa thiết kế, dùng định mức gốc `qty_std`.
    `qty_mode='qty'` = người dùng nhập định mức / nhu cầu tay → dùng `qty`.
    """
    mode = str(row.get('qty_mode') or '').strip().lower()
    if row.get('material_group_id') and row.get('qty_std') not in (None, ''):
        # NPL bung từ nhóm gom: người lên đơn chia nhu cầu theo size — thiết kế giữ ĐM nhóm.
        return _d(row.get('qty_std'))
    if mode == 'pct' and row.get('qty_std') not in (None, ''):
        return _d(row.get('qty_std'))
    return _d(row.get('qty'))


def _bom_sig(rows) -> list[tuple]:
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = str(r.get('material_code') or '').strip().casefold()
        if not code and not r.get('bom_line_id'):
            continue
        out.append((
            code or f"#{r.get('bom_line_id')}",
            '' if r.get('material_group_id') else str(r.get('size_code') or '').strip().casefold(),
            design_qty(r),
            _d(r.get('scrap_pct'), _Q2),
        ))
    return sorted(out)


def order_line_bom_changed(order_line: SxSalesOrderLine) -> bool:
    """BOM trên đơn khác phiên bản BOM hồ sơ đang trỏ tới?"""
    rows = list(order_line.bom_line_overrides or [])
    if not rows:
        return False
    if not order_line.bom_version_id:
        return True
    from san_xuat.services.sales_orders import bom_lines_snapshot

    return _bom_sig(rows) != _bom_sig(
        bom_lines_snapshot(order_line.bom_version_id, size_qtys=order_line.size_qtys)
    )


def _ob_sig(lines) -> list[tuple]:
    return [
        (
            (ln.op_code or '').strip().casefold(),
            _d(ln.qty_per_garment, Decimal('0.001')),
            _d(ln.applied_unit_smv),
            ln.work_center_id or (ln.work_center_code or '').strip().casefold(),
        )
        for ln in sorted(lines, key=lambda x: (x.seq_no or 0, x.pk or 0))
    ]


def order_line_ob_changed(order_line: SxSalesOrderLine) -> bool:
    """OB trên đơn (công đoạn / SMV đơn hàng) khác OB hồ sơ đang trỏ tới?"""
    order_lines = list(order_line.routing_lines.all())
    if not order_lines:
        return False
    if not order_line.routing_id or order_line.routing is None:
        return True
    return _ob_sig(order_lines) != _ob_sig(list(order_line.routing.lines.all()))


def order_edited_lines(order: SxSalesOrder) -> dict[str, set[int]]:
    """Dòng đơn có lịch sử *sửa trên đơn* (BOM / OB) sau lần Cập nhật về hồ sơ gần nhất.

    Lệch do hồ sơ thiết kế đổi sau khi lên đơn, hoặc do phân bổ % theo size, KHÔNG tính là sửa.
    """
    from san_xuat.hub_models import SxPlanAuditLog

    logs = SxPlanAuditLog.objects.filter(
        object_type='SxSalesOrder', object_id=str(order.pk),
    ).order_by('created_at', 'id').values('changes', 'summary', 'created_at')
    edited: dict[str, dict[int, object]] = {'bom': {}, 'ob': {}}
    last_publish: dict[str, object] = {'bom': None, 'ob': None}
    for log in logs:
        ch = log['changes'] if isinstance(log['changes'], dict) else {}
        kind = ch.get('kind') or ''
        if 'items' in ch and 'repoint' in ch:
            k = kind.replace('publish_', '') if kind else ''
            if k in last_publish:
                last_publish[k] = log['created_at']
            continue
        if not kind and 'line_id' in ch and 'before' in ch and 'after' in ch:
            kind = 'bom'  # nhật ký sửa BOM đời cũ
        if kind in edited and ch.get('line_id'):
            try:
                edited[kind][int(ch['line_id'])] = log['created_at']
            except (TypeError, ValueError):
                continue
    out: dict[str, set[int]] = {}
    for k, rows in edited.items():
        cut = last_publish[k]
        out[k] = {lid for lid, at in rows.items() if cut is None or at > cut}
    return out


def order_tech_changes(order: SxSalesOrder, *, edited: dict | None = None) -> dict:
    """{'bom': bool, 'ob': bool} — có dòng đã SỬA TRÊN ĐƠN và còn khác hồ sơ."""
    edited = edited if edited is not None else order_edited_lines(order)
    bom = ob = False
    for ln in order.lines.all():
        if not bom and ln.pk in edited['bom'] and order_line_bom_changed(ln):
            bom = True
        if not ob and ln.pk in edited['ob'] and order_line_ob_changed(ln):
            ob = True
        if bom and ob:
            break
    return {'bom': bom, 'ob': ob}


def _order_note(order: SxSalesOrder) -> str:
    return f'Cập nhật từ ĐH {order.code}'


def _bom_rows_for_line(order_line: SxSalesOrderLine) -> list[dict]:
    rows = list(order_line.bom_line_overrides or [])
    if rows:
        return [r for r in rows if isinstance(r, dict)]
    if order_line.bom_version_id:
        from san_xuat.services.sales_orders import bom_lines_snapshot

        return bom_lines_snapshot(order_line.bom_version_id)
    return []


def _resolve_material(code: str, bom_line_id):
    from kho_npl.models import Material
    from san_xuat.models import BomLine

    src_line = None
    if bom_line_id:
        try:
            src_line = (
                BomLine.objects.select_related('material', 'substitute_material')
                .filter(pk=int(bom_line_id))
                .first()
            )
        except (TypeError, ValueError):
            src_line = None
    code = (code or '').strip()
    if src_line is not None and src_line.material_id and (
        not code or (src_line.material.code or '').strip().casefold() == code.casefold()
    ):
        return src_line.material, src_line
    if not code:
        return None, None
    mat = Material.objects.filter(code__iexact=code).order_by('-pk').first()
    if src_line is not None and mat is not None:
        if src_line.material_id == mat.pk:
            return mat, src_line
        if not src_line.material_id and src_line.material_group_id and mat.material_group_id == src_line.material_group_id:
            return mat, src_line
    return mat, None


def _regroup_planned(planned: list[tuple], rows: list[dict]) -> list[tuple]:
    """Gộp lại các NPL bung từ cùng 1 dòng nhóm → 1 dòng nhóm trên BOM mới.

    Chỉ gộp khi đủ mọi thành viên đang dùng của nhóm và cùng ĐM / hao hụt / size;
    nếu không, giữ các dòng NPL lẻ. Kết quả: (idx_list, mat|None, group|None, src_line, qty, scrap, size).
    """
    from kho_npl.models import MaterialGroup
    from san_xuat.services.bom_group import group_members_map

    by_key: dict[tuple, list[tuple]] = {}
    for item in planned:
        idx = item[0]
        row = rows[idx - 1] if 0 < idx <= len(rows) else {}
        gid = row.get('material_group_id') if isinstance(row, dict) else None
        if gid:
            by_key.setdefault((int(gid), row.get('bom_line_id') or 0), []).append(item)
    members = group_members_map(k[0] for k in by_key)
    groups = MaterialGroup.objects.in_bulk([k[0] for k in by_key])
    merged_first: dict[int, tuple] = {}
    merged_skip: set[int] = set()
    for (gid, _bid), items in by_key.items():
        group = groups.get(gid)
        member_ids = {m.pk for m in members.get(gid, [])}
        item_ids = {it[1].pk for it in items}
        same = len({(it[3], it[4], it[5]) for it in items}) == 1
        if group is None or not same or not member_ids or item_ids != member_ids or len(items) != len(member_ids):
            continue
        first = items[0]
        merged_first[first[0]] = (
            [it[0] for it in items], None, group, first[2], first[3], first[4], first[5],
        )
        merged_skip.update(it[0] for it in items[1:])
    out = []
    for item in planned:
        idx = item[0]
        if idx in merged_skip:
            continue
        if idx in merged_first:
            out.append(merged_first[idx])
        else:
            out.append(([idx], item[1], None, item[2], item[3], item[4], item[5]))
    return out


@transaction.atomic
def publish_bom_for_line(
    order_line: SxSalesOrderLine,
    *,
    user=None,
    repoint: bool = True,
) -> PublishLineResult:
    """Tao BOM moi (dang ap dung) tren ho so tu snapshot BOM cua dong don."""
    from san_xuat.models import BomLine, BomVersion, SxBomAuditLog
    from san_xuat.services.bom import create_bom_version, set_bom_status
    from san_xuat.services.bom_audit import bom_snapshot, log_bom_event

    order = order_line.order
    res = PublishLineResult(product_code=order_line.product_code or '')
    doc = _doc_for_line(order_line)
    if doc is None:
        raise OrderTechPublishError(f'{order_line.product_code}: chưa có hồ sơ thiết kế.')
    res.doc_code = doc.product_code or ''
    res.doc_id = doc.pk
    rows = _bom_rows_for_line(order_line)
    if not rows:
        raise OrderTechPublishError(f'{order_line.product_code}: đơn chưa có BOM để cập nhật.')

    base = order_line.bom_version if order_line.bom_version_id else None
    planned: list[tuple] = []
    for idx, row in enumerate(rows, start=1):
        code = str(row.get('material_code') or '').strip()
        mat, src_line = _resolve_material(code, row.get('bom_line_id'))
        if mat is None:
            res.skipped.append(code or f"dòng {idx}")
            continue
        qty = design_qty(row)
        if qty < 0:
            qty = Decimal('0').quantize(_Q4)
        scrap = _d(row.get('scrap_pct'), _Q2)
        size_code = str(row.get('size_code') or '').strip()[:20]
        if row.get('material_group_id') and src_line is not None and not src_line.material_id:
            # Size gán tự động theo NPL lẻ trên đơn — thiết kế giữ size của dòng nhóm.
            size_code = (src_line.size_code or '').strip()[:20]
        planned.append((idx, mat, src_line, qty, scrap, size_code))
    if not planned:
        raise OrderTechPublishError(
            f'{order_line.product_code}: không có NPL hợp lệ trong danh mục để tạo BOM.'
        )

    bom = create_bom_version(doc, user=user)
    bom.notes = _order_note(order)[:2000]
    if base is not None:
        bom.overhead_pct = base.overhead_pct
        bom.overhead_amount = base.overhead_amount
        bom.other_cost_amount = base.other_cost_amount
        bom.routing = base.routing
        base_notes = (base.notes or '').strip()
        if base_notes:
            bom.notes = f'{bom.notes}\n{base_notes}'
    bom.save()
    new_ids: dict[int, int] = {}
    grouped_pks: set[int] = set()
    for sort_no, (idx_list, mat, group, src_line, qty, scrap, size_code) in enumerate(
        _regroup_planned(planned, rows), start=1,
    ):
        new_pk = BomLine.objects.create(
            bom=bom,
            material=mat,
            material_group=group,
            substitute_material=src_line.substitute_material if src_line else None,
            qty=qty,
            scrap_pct=scrap,
            size_code=size_code,
            notes=(src_line.notes if src_line else '') or '',
            sort_order=sort_no,
        ).pk
        if group is not None:
            grouped_pks.add(new_pk)
        for idx in idx_list:
            new_ids[idx] = new_pk
    if base is not None:
        from san_xuat.models import ProcessStep

        for step in base.process_steps.all().order_by('sequence', 'id'):
            step.pk = None
            step.id = None
            step.bom = bom
            step.save()

    bom = set_bom_status(bom, BomVersion.STATUS_ACTIVE)
    log_bom_event(
        bom=bom,
        action=SxBomAuditLog.ACTION_NEW_VERSION,
        summary=(
            f'Tạo {bom.version_label} từ ĐH {order.code}'
            + (f' (gốc {base.version_label})' if base is not None else '')
        ),
        changes={
            'source_order_id': order.pk,
            'source_order_code': order.code,
            'source_order_line_id': order_line.pk,
            'base_bom_id': base.pk if base is not None else None,
            'skipped_codes': res.skipped,
            'after': bom_snapshot(bom),
        },
        user=user,
    )
    if repoint:
        # Giu nguyen snapshot don (SL/hao hut), chi gan lai id dong BOM moi + dinh muc chuan moi.
        remapped = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            item = dict(row)
            if idx in new_ids:
                item['bom_line_id'] = new_ids[idx]
                if new_ids[idx] not in grouped_pks:
                    item.pop('material_group_id', None)
                    item.pop('group_name', None)
                if str(item.get('qty_mode') or '').lower() != 'pct':
                    item['qty_std'] = item.get('qty')
                    item['qty_pct'] = 100.0
            remapped.append(item)
        order_line.bom_version = bom
        order_line.bom_line_overrides = remapped
        order_line.save(update_fields=['bom_version', 'bom_line_overrides'])
    res.label = bom.version_label
    res.n_lines = len(planned)
    return res


def _latest_writable_bom(doc):
    from san_xuat.models import BomVersion
    from san_xuat.services.tech_doc_copy import is_bom_locked

    for bom in doc.bom_versions.exclude(status=BomVersion.STATUS_ARCHIVED).order_by('-created_at', '-id'):
        if not is_bom_locked(bom):
            return bom
    return None


@transaction.atomic
def publish_ob_for_line(
    order_line: SxSalesOrderLine,
    *,
    user=None,
    repoint: bool = True,
) -> PublishLineResult:
    """Tao OB (routing) REV moi, da duyet, tu snapshot cong doan cua dong don."""
    from san_xuat.ie_models import SxRouting, SxRoutingLine
    from san_xuat.services.ie_ops import IeOpsError, approve_routing, create_blank_routing

    order = order_line.order
    res = PublishLineResult(product_code=order_line.product_code or '')
    doc = _doc_for_line(order_line)
    if doc is None:
        raise OrderTechPublishError(f'{order_line.product_code}: chưa có hồ sơ thiết kế.')
    res.doc_code = doc.product_code or ''
    res.doc_id = doc.pk
    src_lines = list(
        order_line.routing_lines.select_related('source_routing_line').order_by('seq_no', 'id')
    )
    if not src_lines:
        raise OrderTechPublishError(f'{order_line.product_code}: đơn chưa có công đoạn OB để cập nhật.')

    base: SxRouting | None = order_line.routing
    try:
        routing = create_blank_routing(tech_doc=doc, user=user)
    except IeOpsError as exc:
        raise OrderTechPublishError(str(exc)) from exc
    # create_blank_routing co the tu gan vao BOM chua co routing; ta gan lai theo quy tac rieng.
    if base is not None:
        routing.style_name = base.style_name or routing.style_name
        routing.product_family = base.product_family or routing.product_family
    routing.notes = _order_note(order)[:255]
    routing.save(update_fields=['style_name', 'product_family', 'notes', 'updated_at'])

    used: set[int] = set()
    for i, src in enumerate(src_lines, start=1):
        seq = int(src.seq_no or i * 10)
        while seq in used:
            seq += 1
        used.add(seq)
        ref = src.source_routing_line
        lib_smv = (
            ref.library_unit_smv if ref is not None and ref.library_unit_smv
            else (src.library_unit_smv or Decimal('0'))
        )
        SxRoutingLine.objects.create(
            routing=routing,
            seq_no=seq,
            operation_id=src.operation_id,
            op_code=(src.op_code or '')[:30],
            op_rev=(src.op_rev or 'R01')[:10],
            op_name_vi=(src.op_name_vi or '')[:200],
            group_code=(src.group_code or '')[:30],
            qty_per_garment=src.qty_per_garment or Decimal('1'),
            library_unit_smv=lib_smv,
            applied_unit_smv=src.applied_unit_smv or Decimal('0'),
            price_factor=src.price_factor or Decimal('0'),
            total_unit_price=src.total_unit_price or Decimal('0'),
            machine_id=src.machine_id,
            machine_code=(src.machine_code or '')[:40],
            work_center_id=src.work_center_id,
            work_center_code=(src.work_center_code or '')[:40],
            count_minutes=src.count_minutes or Decimal('0'),
            transfer_minutes=src.transfer_minutes or Decimal('0'),
            predecessor_seq=getattr(ref, 'predecessor_seq', None) if ref is not None else None,
            parallel_group=(getattr(ref, 'parallel_group', '') or '') if ref is not None else '',
            bundle_size=getattr(ref, 'bundle_size', None) if ref is not None else None,
            skill_level_label=(src.skill_level_label or '')[:60],
            critical_qc=bool(src.critical_qc),
            target_efficiency=(getattr(ref, 'target_efficiency', None) or Decimal('0')) if ref is not None else Decimal('0'),
            notes=(src.notes or '')[:255],
            variance_explanation=(src.variance_explanation or '')[:500],
        )

    try:
        routing = approve_routing(routing=routing, user=user)
    except IeOpsError as exc:
        raise OrderTechPublishError(f'{order_line.product_code}: {exc}') from exc

    # Gan OB moi vao BOM moi nhat con sua duoc (chua gan LSX) + dung lai cong doan BOM.
    target_bom = _latest_writable_bom(doc)
    if target_bom is not None:
        from san_xuat.services.tech_doc_copy import _rebuild_process_steps_from_routing

        target_bom.routing = routing
        target_bom.save(update_fields=['routing', 'updated_at'])
        target_bom.process_steps.all().delete()
        _rebuild_process_steps_from_routing(target_bom, routing)

    from san_xuat.ie_models import SxIeAuditLog
    from san_xuat.services.ie_audit import log_ie_event

    log_ie_event(
        action=SxIeAuditLog.ACTION_CREATE,
        summary=f'Tạo OB {routing.routing_id} từ ĐH {order.code} ({len(src_lines)} CĐ)',
        object_type='SxRouting',
        object_id=routing.pk,
        object_repr=routing.routing_id,
        user=user,
    )

    if repoint:
        order_line.routing = routing
        order_line.save(update_fields=['routing'])
        new_by_seq = {ln.seq_no: ln.pk for ln in routing.lines.all()}
        used2: set[int] = set()
        for i, src in enumerate(src_lines, start=1):
            seq = int(src.seq_no or i * 10)
            while seq in used2:
                seq += 1
            used2.add(seq)
            new_id = new_by_seq.get(seq)
            if new_id and src.source_routing_line_id != new_id:
                type(src).objects.filter(pk=src.pk).update(source_routing_line_id=new_id)
    res.label = routing.routing_rev
    res.n_lines = len(src_lines)
    if target_bom is not None:
        res.linked_bom = target_bom.version_label
    return res


def publish_order_tech(order: SxSalesOrder, *, kind: str, user=None, repoint: bool = True) -> PublishResult:
    """Chay cho tat ca dong san pham cua don. Moi dong 1 transaction rieng."""
    from san_xuat.services.order_routing import assert_order_routing_editable
    from san_xuat.services.plan_audit import log_plan_action

    if kind not in {'bom', 'ob'}:
        raise OrderTechPublishError('Loại cập nhật không hợp lệ.')
    try:
        assert_order_routing_editable(order)
    except Exception as exc:
        raise OrderTechPublishError(str(exc)) from exc
    fn = publish_bom_for_line if kind == 'bom' else publish_ob_for_line
    changed_fn = order_line_bom_changed if kind == 'bom' else order_line_ob_changed
    edited_ids = order_edited_lines(order)[kind]
    result = PublishResult(kind=kind)
    seen_docs: set[int] = set()
    for ln in order.lines.select_related('bom_version__tech_doc', 'routing').order_by('sort_order', 'id'):
        if ln.pk not in edited_ids or not changed_fn(ln):
            continue
        doc = _doc_for_line(ln)
        if doc is not None and doc.pk in seen_docs:
            # Cung ho so (trung SP) chi tao 1 phien ban.
            continue
        try:
            item = fn(ln, user=user, repoint=repoint)
        except OrderTechPublishError as exc:
            item = PublishLineResult(product_code=ln.product_code or '', error=str(exc))
        else:
            if doc is not None:
                seen_docs.add(doc.pk)
        result.items.append(item)
    if not result.items:
        return result
    log_plan_action(
        action='update',
        obj=order,
        summary=(
            f"Cập nhật {'BOM' if kind == 'bom' else 'OB'} về hồ sơ thiết kế: "
            + ', '.join(f'{it.doc_code} {it.label}' for it in result.ok_items)
        ),
        changes={
            'kind': f'publish_{kind}',
            'repoint': repoint,
            'items': [
                {'product_code': it.product_code, 'doc': it.doc_code, 'doc_id': it.doc_id,
                 'label': it.label, 'n_lines': it.n_lines, 'skipped': it.skipped,
                 'linked_bom': it.linked_bom, 'error': it.error}
                for it in result.items
            ],
        },
        user=user,
    )
    return result
