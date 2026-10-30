"""Lịch sử chỉnh sửa đơn đặt hàng — gom nhật ký và chuẩn hóa diff để hiển thị chi tiết."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from san_xuat.hub_models import SxSalesOrder, SxSalesOrderLine


# --------------------------------------------------------------------------- format


def _num(value) -> str:
    from san_xuat.templatetags.sx_format import format_sx_num

    if value in (None, ''):
        return '—'
    try:
        return format_sx_num(Decimal(str(value)))
    except Exception:
        return str(value)


def _txt(value) -> str:
    text = str(value if value is not None else '').strip()
    return text or '—'


def _user_label(user, username: str = '') -> str:
    if user is not None:
        full = (user.get_full_name() or '').strip() if hasattr(user, 'get_full_name') else ''
        return full or getattr(user, 'username', '') or username or 'Hệ thống'
    return username or 'Hệ thống'


# --------------------------------------------------------------------------- snapshot


def ob_snapshot(order_line: SxSalesOrderLine) -> list[dict]:
    """Chụp OB trên dòng đơn để so sánh trước / sau."""
    out = []
    for ln in order_line.routing_lines.select_related('work_center').order_by('seq_no', 'id'):
        out.append({
            'seq_no': ln.seq_no,
            'op_code': ln.op_code or '',
            'op_name': ln.op_name_vi or '',
            'qty_per_garment': str(ln.qty_per_garment or 0),
            'library_unit_smv': str(ln.library_unit_smv or 0),
            'applied_unit_smv': str(ln.applied_unit_smv or 0),
            'work_center': (ln.work_center.name if ln.work_center_id else '') or ln.work_center_code or '',
            'machine_code': ln.machine_code or '',
            'variance_explanation': ln.variance_explanation or '',
        })
    return out


def line_ref(order_line: SxSalesOrderLine) -> dict:
    return {
        'line_id': order_line.pk,
        'product_code': order_line.product_code or '',
        'product_name': order_line.product_name or '',
        'bom_version_id': order_line.bom_version_id,
        'bom_label': getattr(order_line.bom_version, 'version_label', '') if order_line.bom_version_id else '',
        'routing_id': order_line.routing_id,
        'routing_rev': getattr(order_line.routing, 'routing_rev', '') if order_line.routing_id else '',
    }


def header_snapshot(order: SxSalesOrder) -> dict:
    return {
        'code': order.code or '',
        'customer_name': order.customer_name or '',
        'request_date': order.request_date.isoformat() if order.request_date else '',
        'due_date': order.due_date.isoformat() if order.due_date else '',
        'notes': order.notes or '',
        'attachment': order.attachment.name if order.attachment else '',
    }


def lines_snapshot(order: SxSalesOrder) -> list[dict]:
    out = []
    for ln in order.lines.select_related('bom_version', 'routing').order_by('sort_order', 'id'):
        out.append({
            'product_code': ln.product_code or '',
            'product_name': ln.product_name or '',
            'qty': str(ln.qty or 0),
            'size_qtys': {str(k): str(v) for k, v in (ln.size_qtys or {}).items()},
            'qty_scrap_rate': str(ln.qty_scrap_rate or 0),
            'uom': ln.uom or '',
            'due_date': ln.due_date.isoformat() if ln.due_date else '',
            'bom_label': ln.bom_version.version_label if ln.bom_version_id and ln.bom_version else '',
            'routing_rev': ln.routing.routing_rev if ln.routing_id and ln.routing else '',
        })
    return out


# --------------------------------------------------------------------------- logging


def log_order_event(*, order: SxSalesOrder, action: str, kind: str, summary: str, user=None, **extra) -> None:
    """Ghi nhật ký gắn với đơn (object SxSalesOrder) + `kind` để lọc trong modal."""
    from san_xuat.services.plan_audit import log_plan_action

    changes = {'kind': kind, **extra}
    log_plan_action(action=action, obj=order, summary=summary, changes=changes, user=user)


# --------------------------------------------------------------------------- diff

_BOM_FIELDS = (
    ('qty', 'ĐM/SP', _num),
    ('scrap_pct', 'Hao hụt %', _num),
    ('unit', 'ĐVT', _txt),
)
_OB_FIELDS = (
    ('op_name', 'Tên CĐ', _txt),
    ('qty_per_garment', 'SL/SP', _num),
    ('applied_unit_smv', 'SMV đơn hàng', _num),
    ('library_unit_smv', 'SMV sản phẩm', _num),
    ('work_center', 'Bộ phận', _txt),
    ('machine_code', 'Máy', _txt),
    ('variance_explanation', 'Giải trình', _txt),
)
_HEADER_FIELDS = (
    ('code', 'Số đơn', _txt),
    ('customer_name', 'Khách hàng', _txt),
    ('request_date', 'Ngày dự kiến thực hiện', _txt),
    ('due_date', 'Ngày dự kiến hoàn thành', _txt),
    ('notes', 'Ghi chú', _txt),
    ('attachment', 'File đính kèm', _txt),
)
_LINE_FIELDS = (
    ('product_name', 'Tên SP', _txt),
    ('qty', 'Số lượng', _num),
    ('qty_scrap_rate', 'Tỷ lệ sai hỏng %', _num),
    ('uom', 'ĐVT', _txt),
    ('due_date', 'Hạn giao', _txt),
    ('bom_label', 'BOM', _txt),
    ('routing_rev', 'OB', _txt),
)


def _field_diffs(old: dict, new: dict, spec) -> list[dict]:
    out = []
    for key, label, fmt in spec:
        a, b = fmt(old.get(key)), fmt(new.get(key))
        if a != b:
            out.append({'label': label, 'before': a, 'after': b})
    return out


def _bom_key(row: dict) -> tuple:
    return (
        str(row.get('material_code') or '').strip().casefold() or f"#{row.get('bom_line_id')}",
        str(row.get('size_code') or '').strip().casefold(),
    )


def _bom_title(row: dict) -> str:
    code = str(row.get('material_code') or '').strip()
    name = str(row.get('material_name') or '').strip()
    size = str(row.get('size_code') or '').strip()
    title = f'{code} — {name}' if code and name else (code or name or 'NPL')
    return f'{title} · size {size}' if size else title


def _diff_rows(before, after, *, key, title, spec, brief) -> dict:
    before = [r for r in (before or []) if isinstance(r, dict)]
    after = [r for r in (after or []) if isinstance(r, dict)]
    bmap = {key(r): r for r in before}
    amap = {key(r): r for r in after}
    added = [{'title': title(r), 'detail': brief(r)} for k, r in amap.items() if k not in bmap]
    removed = [{'title': title(r), 'detail': brief(r)} for k, r in bmap.items() if k not in amap]
    changed = []
    for k, r in amap.items():
        if k in bmap:
            diffs = _field_diffs(bmap[k], r, spec)
            if diffs:
                changed.append({'title': title(r), 'diffs': diffs})
    return {
        'added': added, 'removed': removed, 'changed': changed,
        'n_before': len(before), 'n_after': len(after),
    }


def diff_bom(before, after) -> dict:
    return _diff_rows(
        before, after, key=_bom_key, title=_bom_title, spec=_BOM_FIELDS,
        brief=lambda r: f"ĐM {_num(r.get('qty'))} {r.get('unit') or ''} · HH {_num(r.get('scrap_pct'))}%".strip(),
    )


def _ob_key(row: dict) -> tuple:
    return (str(row.get('op_code') or '').strip().casefold(), str(row.get('seq_no') or ''))


def _ob_title(row: dict) -> str:
    seq = row.get('seq_no')
    code = row.get('op_code') or ''
    name = row.get('op_name') or ''
    return f"#{seq} {code}" + (f' — {name}' if name else '')


def diff_ob(before, after) -> dict:
    return _diff_rows(
        before, after, key=_ob_key, title=_ob_title, spec=_OB_FIELDS,
        brief=lambda r: f"SMV đơn {_num(r.get('applied_unit_smv'))} · SL/SP {_num(r.get('qty_per_garment'))}",
    )


def _line_key(row: dict) -> str:
    return str(row.get('product_code') or '').strip().casefold()


def diff_lines(before, after) -> dict:
    def brief(r):
        sizes = r.get('size_qtys') or {}
        size_txt = ', '.join(f'{k}: {_num(v)}' for k, v in sizes.items())
        return f"SL {_num(r.get('qty'))}" + (f' ({size_txt})' if size_txt else '')

    res = _diff_rows(
        before, after, key=_line_key,
        title=lambda r: f"{r.get('product_code') or ''} — {r.get('product_name') or ''}".strip(' —'),
        spec=_LINE_FIELDS, brief=brief,
    )
    # Size: so riêng từng size
    bmap = {_line_key(r): r for r in before or [] if isinstance(r, dict)}
    for r in after or []:
        if not isinstance(r, dict) or _line_key(r) not in bmap:
            continue
        old_s = bmap[_line_key(r)].get('size_qtys') or {}
        new_s = r.get('size_qtys') or {}
        diffs = [
            {'label': f'Size {s}', 'before': _num(old_s.get(s)), 'after': _num(new_s.get(s))}
            for s in sorted(set(old_s) | set(new_s))
            if _num(old_s.get(s)) != _num(new_s.get(s))
        ]
        if diffs:
            title = f"{r.get('product_code') or ''} — {r.get('product_name') or ''}".strip(' —')
            hit = next((c for c in res['changed'] if c['title'] == title), None)
            if hit:
                hit['diffs'].extend(diffs)
            else:
                res['changed'].append({'title': title, 'diffs': diffs})
    return res


# --------------------------------------------------------------------------- events

KIND_META = {
    'order': ('Thông tin đơn', 'bi-file-earmark-text', 'slate'),
    'lines': ('Dòng sản phẩm', 'bi-box-seam', 'indigo'),
    'confirm': ('Xác nhận', 'bi-patch-check', 'blue'),
    'bom': ('BOM trên đơn', 'bi-diagram-3', 'amber'),
    'ob': ('OB trên đơn', 'bi-list-ol', 'teal'),
    'publish_bom': ('Cập nhật BOM về hồ sơ', 'bi-cloud-upload', 'red'),
    'publish_ob': ('Cập nhật OB về hồ sơ', 'bi-cloud-upload', 'red'),
    'plan': ('Kế hoạch SX', 'bi-kanban', 'violet'),
    'npl': ('NPL / KHSX', 'bi-boxes', 'green'),
    'mo': ('Lệnh SX', 'bi-gear', 'orange'),
}


@dataclass
class HistoryEvent:
    at: datetime
    user: str
    kind: str
    title: str
    summary: str = ''
    product: str = ''
    fields: list = field(default_factory=list)
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    links: list = field(default_factory=list)
    stats: str = ''

    @property
    def kind_label(self) -> str:
        return KIND_META.get(self.kind, ('Khác', 'bi-dot', 'slate'))[0]

    @property
    def icon(self) -> str:
        return KIND_META.get(self.kind, ('', 'bi-dot', 'slate'))[1]

    @property
    def tone(self) -> str:
        return KIND_META.get(self.kind, ('', '', 'slate'))[2]

    @property
    def has_detail(self) -> bool:
        return bool(self.fields or self.added or self.removed or self.changed or self.notes or self.links)


def _apply_diff(ev: HistoryEvent, diff: dict) -> None:
    ev.added = diff.get('added') or []
    ev.removed = diff.get('removed') or []
    ev.changed = diff.get('changed') or []


def _event_from_order_log(log, order: SxSalesOrder) -> HistoryEvent:
    ch = log.changes if isinstance(log.changes, dict) else {}
    kind = ch.get('kind') or ''
    user = _user_label(log.user, log.username)
    ev = HistoryEvent(at=log.created_at, user=user, kind=kind or 'order', title=log.summary or '', summary='')

    if not kind:
        # Bản ghi cũ: update_order_line_bom_overrides / reload_tech / publish
        if 'before' in ch and 'after' in ch and 'line_id' in ch:
            ev.kind = 'bom'
            ev.title = log.summary
            _apply_diff(ev, diff_bom(ch.get('before'), ch.get('after')))
            ev.stats = f"{len(ch.get('before') or [])} → {len(ch.get('after') or [])} NPL"
        elif log.action in ('reload_tech', 'reload_order_tech'):
            ev.kind = 'plan'
            bits = []
            if ch.get('bom'):
                bits.append(f"BOM: {ch['bom']} dòng")
            if ch.get('routing'):
                bits.append(f"OB: {ch['routing']} dòng")
            if ch.get('npl'):
                bits.append('Đã tính lại NPL')
            ev.notes = bits
        return ev
    if kind in ('bom', 'ob') and 'items' in ch and 'repoint' in ch:
        # Bản ghi publish đời đầu (kind='bom'/'ob')
        kind = ev.kind = f'publish_{kind}'

    if kind in ('bom',):
        _apply_diff(ev, diff_bom(ch.get('before'), ch.get('after')))
        ev.product = ch.get('product') or ''
        ev.stats = f"{len(ch.get('before') or [])} → {len(ch.get('after') or [])} NPL"
        if ch.get('npl_deferred'):
            ev.notes.append('NPL KHSX sẽ tính khi đơn được xác nhận / bỏ tạm giữ.')
    elif kind == 'ob':
        _apply_diff(ev, diff_ob(ch.get('before'), ch.get('after')))
        ev.product = ch.get('product') or ''
        b_smv = sum(Decimal(str(r.get('applied_unit_smv') or 0)) * Decimal(str(r.get('qty_per_garment') or 1)) for r in ch.get('before') or [])
        a_smv = sum(Decimal(str(r.get('applied_unit_smv') or 0)) * Decimal(str(r.get('qty_per_garment') or 1)) for r in ch.get('after') or [])
        ev.stats = (
            f"{len(ch.get('before') or [])} → {len(ch.get('after') or [])} CĐ · "
            f"Tổng SMV/SP {_num(b_smv)} → {_num(a_smv)}"
        )
        if ch.get('source'):
            ev.notes.append(ch['source'])
    elif kind == 'order':
        ev.fields = _field_diffs(ch.get('before') or {}, ch.get('after') or {}, _HEADER_FIELDS)
        ld = diff_lines(ch.get('lines_before'), ch.get('lines_after'))
        _apply_diff(ev, ld)
        if ld['added'] or ld['removed'] or ld['changed']:
            ev.kind = 'lines' if not ev.fields else 'order'
    elif kind == 'confirm':
        if ch.get('reason'):
            ev.notes.append(f"Lý do: {ch['reason']}")
    elif kind in ('publish_bom', 'publish_ob'):
        label = 'BOM' if kind == 'publish_bom' else 'OB'
        for it in ch.get('items') or []:
            if it.get('error'):
                ev.notes.append(f"✗ {it.get('product_code')}: {it.get('error')}")
                continue
            note = f"Hồ sơ {it.get('doc')}: tạo {label} {it.get('label')} ({it.get('n_lines')} dòng)"
            if it.get('linked_bom'):
                note += f", gắn vào BOM {it['linked_bom']}"
            ev.notes.append(note)
            if it.get('skipped'):
                ev.notes.append(f"Bỏ qua NPL không có trong danh mục: {', '.join(it['skipped'])}")
            if it.get('doc_id'):
                from django.urls import reverse

                tab = 'bom' if kind == 'publish_bom' else 'process'
                ev.links.append({
                    'label': f"Mở hồ sơ {it.get('doc')} — {label} {it.get('label')}",
                    'url': reverse('san_xuat:doc_detail', args=[it['doc_id']]) + f'?tab={tab}',
                })
        ev.notes.append(
            'Đơn đã trỏ sang phiên bản mới.' if ch.get('repoint') else 'Đơn vẫn giữ phiên bản cũ.'
        )
    return ev


def _event_from_related_log(log) -> HistoryEvent:
    ch = log.changes if isinstance(log.changes, dict) else {}
    user = _user_label(log.user, log.username)
    if log.object_type == 'SxProductionOrder':
        ev = HistoryEvent(at=log.created_at, user=user, kind='mo', title=log.summary or '')
        before = {f"{r.get('op_code')}": r for r in ch.get('before') or [] if isinstance(r, dict)}
        for r in ch.get('after') or []:
            if not isinstance(r, dict):
                continue
            act = r.get('action') or ''
            title = f"{r.get('op_code') or ''} — {r.get('process_name') or ''}".strip(' —')
            if act == 'delete':
                ev.removed.append({'title': title, 'detail': f"LSX {log.object_code}"})
            elif act == 'flag_removed':
                ev.removed.append({'title': title, 'detail': 'Đã có sản lượng — đánh dấu bỏ khỏi OB'})
            elif act == 'add':
                ev.added.append({'title': title, 'detail': f"SMV {_num(r.get('applied_unit_smv'))}"})
            else:
                old = before.get(f"{r.get('op_code')}") or {}
                diffs = _field_diffs(old, r, (('applied_unit_smv', 'SMV', _num),))
                if diffs:
                    ev.changed.append({'title': title, 'diffs': diffs})
        return ev
    ev = HistoryEvent(at=log.created_at, user=user, kind='npl', title=log.summary or '')
    if ch.get('lines') is not None:
        ev.stats = f"{ch.get('lines')} mã NPL"
    return ev


def order_history(order: SxSalesOrder, *, limit: int = 300) -> list[HistoryEvent]:
    """Toàn bộ lịch sử liên quan đến đơn, mới nhất trước."""
    from django.db.models import Q

    from san_xuat.hub_models import SxPlanAuditLog

    events: list[HistoryEvent] = []
    own = SxPlanAuditLog.objects.select_related('user').filter(
        object_type='SxSalesOrder', object_id=str(order.pk),
    )
    for log in own.order_by('-created_at', '-id')[:limit]:
        events.append(_event_from_order_log(log, order))

    mo_ids = [str(pk) for pk in order.production_orders.values_list('pk', flat=True)]
    related = SxPlanAuditLog.objects.select_related('user').filter(
        Q(object_type='SxProductionOrder', object_id__in=mo_ids, changes__order_id=order.pk)
        | Q(object_type='SxMaterialPlan', changes__sales_order=order.code)
    )
    for log in related.order_by('-created_at', '-id')[:limit]:
        events.append(_event_from_related_log(log))

    # Mốc gốc từ chính đơn (luôn có, kể cả đơn cũ chưa ghi nhật ký)
    if order.created_at:
        events.append(HistoryEvent(
            at=order.created_at,
            user=_user_label(order.created_by),
            kind='order',
            title=f'Tạo đơn {order.code}',
            notes=[f'{order.lines.count()} dòng sản phẩm'],
        ))
    has_confirm_log = any(e.kind == 'confirm' and 'Xác nhận' in e.title for e in events)
    if order.confirmed_at and not has_confirm_log:
        events.append(HistoryEvent(
            at=order.confirmed_at,
            user=_user_label(order.confirmed_by),
            kind='confirm',
            title=f'Xác nhận đơn {order.code}',
        ))

    events.sort(key=lambda e: e.at, reverse=True)
    return events[:limit]


def history_summary(events: list[HistoryEvent]) -> list[dict]:
    """Đếm theo nhóm để làm bộ lọc trong modal."""
    counts: dict[str, int] = {}
    for e in events:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    return [
        {'kind': k, 'label': KIND_META.get(k, ('Khác',))[0], 'count': n}
        for k, n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
