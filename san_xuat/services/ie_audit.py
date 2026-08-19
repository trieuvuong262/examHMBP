"""Ghi nhật ký thao tác IE master data."""

from __future__ import annotations

from san_xuat.ie_models import SxIeAuditLog


def log_ie_event(
    *,
    action: str,
    summary: str = '',
    object_type: str = '',
    object_id: str | int = '',
    object_repr: str = '',
    changes: dict | None = None,
    user=None,
) -> SxIeAuditLog:
    username = ''
    if user is not None and getattr(user, 'is_authenticated', False):
        username = getattr(user, 'username', '') or ''
    elif user is not None:
        username = getattr(user, 'username', '') or str(user)
    return SxIeAuditLog.objects.create(
        action=action,
        object_type=(object_type or '')[:40],
        object_id=str(object_id or '')[:80],
        object_repr=(object_repr or '')[:255],
        summary=(summary or '')[:500],
        changes=changes or {},
        user=user if getattr(user, 'pk', None) else None,
        username=username[:150],
    )


def routing_snapshot(routing) -> dict:
    """Chụp trạng thái OB (toàn bộ công đoạn) để so sánh và khôi phục."""
    lines = []
    for line in routing.lines.select_related('work_center').order_by('seq_no', 'pk'):
        lines.append({
            'seq_no': line.seq_no,
            'op_code': line.op_code or '',
            'op_rev': line.op_rev or 'R01',
            'op_name_vi': line.op_name_vi or '',
            'group_code': line.group_code or '',
            'work_center_code': getattr(line.work_center, 'code', '') or line.work_center_code or '',
            'work_center_name': getattr(line.work_center, 'name', '') or '',
            'library_unit_smv': str(line.library_unit_smv or 0),
        })
    return {
        'routing_id': routing.routing_id,
        'routing_rev': routing.routing_rev,
        'lines': lines,
    }


def routing_diff(before: dict, after: dict) -> dict:
    """So sánh 2 snapshot OB → mô tả công đoạn được thêm / bớt / đổi."""
    def key(item):
        return (item.get('op_code') or '', item.get('op_name_vi') or '')

    def title(item):
        code = (item.get('op_code') or '').strip()
        name = (item.get('op_name_vi') or '').strip()
        return f'{code} — {name}' if code and name else (name or code or 'Công đoạn')

    def detail(item):
        bits = []
        if item.get('group_code'):
            bits.append(f"nhóm {item['group_code']}")
        if item.get('work_center_name') or item.get('work_center_code'):
            bits.append(item.get('work_center_name') or item.get('work_center_code'))
        smv = item.get('library_unit_smv')
        if smv and str(smv) not in ('0', '0.0', '0.00'):
            bits.append(f'SMV {smv}s')
        return ' · '.join(bits)

    before_map = {key(item): item for item in before.get('lines', [])}
    after_map = {key(item): item for item in after.get('lines', [])}

    added = [
        {'title': title(item), 'detail': detail(item)}
        for k, item in after_map.items() if k not in before_map
    ]
    removed = [
        {'title': title(item), 'detail': detail(item)}
        for k, item in before_map.items() if k not in after_map
    ]

    tracked = [
        ('seq_no', 'Thứ tự'),
        ('group_code', 'Nhóm'),
        ('work_center_name', 'Bộ phận'),
        ('library_unit_smv', 'SMV (giây)'),
    ]
    changed = []
    for k, new_item in after_map.items():
        old_item = before_map.get(k)
        if old_item is None:
            continue
        diffs = []
        for field, label in tracked:
            old = str(old_item.get(field, '') or '')
            new = str(new_item.get(field, '') or '')
            if old != new:
                diffs.append({'label': label, 'before': old or '—', 'after': new or '—'})
        if diffs:
            changed.append({'title': title(new_item), 'diffs': diffs})

    result = {}
    if added or removed or changed:
        result['lines'] = {'added': added, 'removed': removed, 'changed': changed}
    return result
