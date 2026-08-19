"""Ghi nhật ký thao tác BOM."""

from __future__ import annotations


def log_bom_event(
    *,
    bom,
    action: str,
    summary: str = '',
    changes: dict | None = None,
    user=None,
):
    from san_xuat.models import SxBomAuditLog

    username = ''
    if user is not None:
        username = getattr(user, 'username', '') or str(user)

    return SxBomAuditLog.objects.create(
        bom=bom,
        action=action,
        summary=(summary or '')[:500],
        changes=changes or {},
        user=user if getattr(user, 'pk', None) else None,
        username=username[:150],
    )


def bom_snapshot(bom) -> dict:
    """Chụp trạng thái BOM (meta + toàn bộ dòng NPL) để so sánh và khôi phục."""
    lines = []
    for line in bom.lines.select_related('material', 'material__unit').order_by('sort_order', 'id'):
        material = line.material
        lines.append({
            'material_id': line.material_id,
            'code': getattr(material, 'code', '') or '',
            'name': getattr(material, 'name', '') or '',
            'unit': getattr(getattr(material, 'unit', None), 'name', '') or '',
            'qty': str(line.qty),
            'scrap_pct': str(line.scrap_pct),
            'size_code': line.size_code or '',
            'notes': line.notes or '',
            'sort_order': line.sort_order,
        })
    return {
        'version_label': bom.version_label,
        'overhead_pct': str(bom.overhead_pct),
        'overhead_amount': str(bom.overhead_amount),
        'notes': bom.notes or '',
        'lines': lines,
    }


BOM_FIELD_LABELS = {
    'version_label': 'Phiên bản',
    'overhead_pct': 'Phụ phí (%)',
    'overhead_amount': 'SX chung / SP',
    'notes': 'Ghi chú',
}


def _line_key(line: dict):
    return (line.get('material_id'), line.get('size_code') or '')


def _line_title(line: dict) -> str:
    code = (line.get('code') or '').strip()
    name = (line.get('name') or '').strip()
    size = (line.get('size_code') or '').strip()
    title = f'{code} — {name}' if code and name else (code or name or 'NPL')
    return f'{title} (size {size})' if size else title


def bom_diff(before: dict, after: dict) -> dict:
    """So sánh 2 snapshot BOM → dict mô tả thay đổi để hiển thị trong lịch sử."""
    fields = {}
    for key, label in BOM_FIELD_LABELS.items():
        old = str(before.get(key, '') or '')
        new = str(after.get(key, '') or '')
        if old != new:
            fields[label] = {'before': old or '—', 'after': new or '—'}

    before_map = {_line_key(item): item for item in before.get('lines', [])}
    after_map = {_line_key(item): item for item in after.get('lines', [])}

    added, removed, changed = [], [], []

    for key, item in after_map.items():
        if key not in before_map:
            added.append({
                'title': _line_title(item),
                'detail': f"{item.get('qty')} {item.get('unit') or ''}".strip(),
            })

    for key, item in before_map.items():
        if key not in after_map:
            removed.append({
                'title': _line_title(item),
                'detail': f"{item.get('qty')} {item.get('unit') or ''}".strip(),
            })

    tracked = [
        ('qty', 'Định mức'),
        ('scrap_pct', 'Hao hụt (%)'),
        ('notes', 'Ghi chú'),
    ]
    for key, new_item in after_map.items():
        old_item = before_map.get(key)
        if old_item is None:
            continue
        diffs = []
        for field, label in tracked:
            old = str(old_item.get(field, '') or '')
            new = str(new_item.get(field, '') or '')
            if old != new:
                diffs.append({'label': label, 'before': old or '—', 'after': new or '—'})
        if diffs:
            changed.append({'title': _line_title(new_item), 'diffs': diffs})

    result = {}
    if fields:
        result['fields'] = fields
    if added or removed or changed:
        result['lines'] = {'added': added, 'removed': removed, 'changed': changed}
    return result
