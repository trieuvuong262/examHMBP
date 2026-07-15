"""Gom NPL thành nhóm biến thể (kiểu KiotViet) — cùng tên nhóm hàng + màu/mã khác."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from decimal import Decimal

from kho_npl.choices import (
    STOCK_STATUS_BADGE,
    STOCK_STATUS_LABELS,
    STOCK_STATUS_LOW,
    STOCK_STATUS_OK,
    STOCK_STATUS_OUT,
)
from kho_npl.variant_group import normalize_variant_group


def material_group_key(material) -> tuple:
    """Khóa gom: cùng nhóm NPL + tên nhóm hàng + ĐVT."""
    group = normalize_variant_group(getattr(material, 'variant_group', '') or '')
    if not group:
        # Không gom — mỗi mã một dòng riêng
        return (f'material:{material.pk}',)
    return (
        material.category_id,
        group,
        material.unit_id,
    )


def _safe_group_dom_key(key: tuple, representative) -> str:
    """Khóa ổn định, an toàn cho HTML/CSS attribute (không chứa |)."""
    if len(key) == 1 and str(key[0]).startswith('material:'):
        return f'm-{representative.pk}'
    raw = f'{key[0]}::{key[1]}::{key[2]}'
    digest = hashlib.md5(raw.encode('utf-8')).hexdigest()[:12]
    return f'g-{digest}'


def _group_display_name(material) -> str:
    group = normalize_variant_group(getattr(material, 'variant_group', '') or '')
    if group:
        return group
    return material.name or material.code


def group_materials(materials) -> list[dict]:
    """
    Gom danh sách Material thành các dòng nhóm.

    Nhóm ≥ 2 mã → can_expand; mã đơn lẻ giữ hiển thị như trước.
    """
    buckets: OrderedDict[tuple, list] = OrderedDict()
    for material in materials:
        key = material_group_key(material)
        buckets.setdefault(key, []).append(material)

    groups = []
    for key, items in buckets.items():
        items = sorted(items, key=lambda m: ((m.code or '').upper(), m.pk))
        rep = items[0]
        groups.append({
            'key': _safe_group_dom_key(key, rep),
            'group_name': _group_display_name(rep),
            'category': rep.category,
            'unit': rep.unit,
            'materials': items,
            'variant_count': len(items),
            'can_expand': len(items) >= 2,
            'representative': rep,
            'is_active': any(m.is_active for m in items),
            'min_stock': min((m.min_stock for m in items), default=Decimal('0')),
            'supplier': next((m.supplier for m in items if m.supplier_id), None),
        })
    return groups


def group_stock_rows(stock_rows: list[dict]) -> list[dict]:
    """
    Gom các stock row (từ material_stock_rows) theo nhóm biến thể.

    Dòng cha: tổng tồn / giá trị / đơn giá BQ / trạng thái xấu nhất.
    """
    buckets: OrderedDict[tuple, list] = OrderedDict()
    for row in stock_rows:
        material = row['material']
        key = material_group_key(material)
        buckets.setdefault(key, []).append(row)

    groups = []
    for key, rows in buckets.items():
        rows = sorted(rows, key=lambda r: ((r['material'].code or '').upper(), r['material'].pk))
        materials = [r['material'] for r in rows]
        rep = rows[0]['material']

        total_qty = sum((r['total_qty'] for r in rows), Decimal('0'))
        stock_value = sum((r.get('stock_value') or Decimal('0') for r in rows), Decimal('0'))
        if total_qty > 0:
            avg_unit_price = (stock_value / total_qty).quantize(Decimal('0.01'))
        else:
            avg_unit_price = Decimal('0')

        statuses = {r['status'] for r in rows}
        if STOCK_STATUS_OUT in statuses:
            status = STOCK_STATUS_OUT
        elif STOCK_STATUS_LOW in statuses:
            status = STOCK_STATUS_LOW
        else:
            status = STOCK_STATUS_OK

        min_stock = min((m.min_stock for m in materials), default=Decimal('0'))

        groups.append({
            'key': _safe_group_dom_key(key, rep),
            'group_name': _group_display_name(rep),
            'category': rep.category,
            'unit': rep.unit,
            'materials': materials,
            'rows': rows,
            'variant_count': len(rows),
            'can_expand': len(rows) >= 2,
            'representative': rep,
            'total_qty': total_qty,
            'avg_unit_price': avg_unit_price,
            'stock_value': stock_value,
            'min_stock': min_stock,
            'status': status,
            'status_label': STOCK_STATUS_LABELS[status],
            'status_badge': STOCK_STATUS_BADGE[status],
            'is_active': any(m.is_active for m in materials),
        })
    return groups


def sort_catalog_groups(groups: list[dict], sort_key: str, sort_dir: str) -> list[dict]:
    reverse = sort_dir == 'desc'

    def key_fn(g: dict):
        rep = g['representative']
        mapping = {
            'code': (g['group_name'] or '').lower(),
            'name': (g['group_name'] or '').lower(),
            'category': (g['category'].name if g.get('category') else '').lower(),
            'color': '',
            'specification': '',
            'unit': (g['unit'].name if g.get('unit') else '').lower(),
            'supplier': (g['supplier'].name if g.get('supplier') else '').lower(),
            'min_stock': g.get('min_stock') or Decimal('0'),
            'status': 1 if g.get('is_active') else 0,
            'variant_group': (g['group_name'] or '').lower(),
        }
        return mapping.get(sort_key, (g['group_name'] or '').lower()), (rep.code or '').lower()

    return sorted(groups, key=key_fn, reverse=reverse)


def sort_stock_groups(groups: list[dict], sort_key: str, sort_dir: str) -> list[dict]:
    reverse = sort_dir == 'desc'

    def key_fn(g: dict):
        mapping = {
            'code': (g['group_name'] or '').lower(),
            'name': (g['group_name'] or '').lower(),
            'category': (g['category'].name if g.get('category') else '').lower(),
            'color': '',
            'unit': (g['unit'].name if g.get('unit') else '').lower(),
            'total_qty': g.get('total_qty') or Decimal('0'),
            'avg_unit_price': g.get('avg_unit_price') or Decimal('0'),
            'stock_value': g.get('stock_value') or Decimal('0'),
            'min_stock': g.get('min_stock') or Decimal('0'),
            'stock_status': g.get('status') or '',
        }
        rep_code = (g['representative'].code or '').lower()
        return mapping.get(sort_key, (g['group_name'] or '').lower()), rep_code

    return sorted(groups, key=key_fn, reverse=reverse)
