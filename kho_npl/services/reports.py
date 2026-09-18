"""Báo cáo xuất nhập tồn — tổng hợp theo mã hàng trên sổ kho."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from kho_npl.material_search import apply_material_search
from kho_npl.models import (
    Material,
    StockAdjustment,
    StockDisposal,
    StockIssue,
    StockLedger,
    StockReceipt,
    Stocktake,
    StockTransfer,
)
from kho_npl.services.scrap_warehouse import exclude_scrap_locations, source_locations_qs
from kho_npl.services.stock import material_stock_rows
from kho_npl.services.variant_groups import group_xnt_rows

DISPLAY_LIMIT = 2000

XNT_COLUMNS = [
    ('group_name', 'Tên nhóm hàng'),
    ('code', 'Mã hàng'),
    ('name', 'Tên hàng'),
    ('qty_open', 'Tồn đầu kỳ'),
    ('val_open', 'Giá trị đầu kỳ'),
    ('qty_in', 'SL Nhập'),
    ('val_in', 'Giá trị nhập'),
    ('qty_out', 'SL Xuất'),
    ('val_out', 'Giá trị xuất'),
    ('qty_close', 'Tồn cuối kỳ'),
    ('val_close', 'Giá trị cuối kỳ'),
]

_DOC_DATE_MODELS = {
    StockLedger.REF_RECEIPT: (StockReceipt, 'receipt_date'),
    StockLedger.REF_ISSUE: (StockIssue, 'issue_date'),
    StockLedger.REF_TRANSFER: (StockTransfer, 'transfer_date'),
    StockLedger.REF_DISPOSAL: (StockDisposal, 'disposal_date'),
    StockLedger.REF_ADJUSTMENT: (StockAdjustment, 'adjust_date'),
    StockLedger.REF_STOCKTAKE: (Stocktake, 'stocktake_date'),
}


def _parse_date(value: str | None, default: date | None = None) -> date | None:
    raw = (value or '').strip()
    if not raw:
        return default
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return default


def _ledger_qs(location_id: int | None = None):
    qs = StockLedger.objects.all()
    if location_id:
        return qs.filter(location_id=location_id)
    return exclude_scrap_locations(qs)


def _zero_bucket() -> dict:
    return {
        'qty_open': Decimal('0'),
        'val_open': Decimal('0'),
        'qty_in': Decimal('0'),
        'val_in': Decimal('0'),
        'qty_out': Decimal('0'),
        'val_out': Decimal('0'),
    }


def _zero_totals() -> dict:
    return {
        **_zero_bucket(),
        'qty_close': Decimal('0'),
        'val_close': Decimal('0'),
    }


def _add_totals(totals: dict, row: dict) -> None:
    for key in totals:
        totals[key] += row[key]


def _line_amount(qty_delta: Decimal, amount: Decimal, unit_price: Decimal, base_price: Decimal) -> Decimal:
    """Thành tiền dòng sổ: ưu tiên amount, rồi đơn giá sổ, rồi giá cơ bản danh mục."""
    amt = amount or Decimal('0')
    if amt > 0:
        return amt
    price = unit_price or Decimal('0')
    if price <= 0:
        price = base_price or Decimal('0')
    return (abs(qty_delta or Decimal('0')) * price).quantize(Decimal('0.01'))


def _doc_dates_for(qs) -> dict[tuple[str, int], date]:
    ids_by_type: dict[str, set[int]] = defaultdict(set)
    for ref_type, ref_id in qs.values_list('ref_type', 'ref_id').distinct():
        if ref_id:
            ids_by_type[ref_type].add(ref_id)
    mapping: dict[tuple[str, int], date] = {}
    for ref_type, (model, field) in _DOC_DATE_MODELS.items():
        ids = ids_by_type.get(ref_type)
        if not ids:
            continue
        for pk, doc_date in model.objects.filter(pk__in=ids).values_list('pk', field):
            if doc_date:
                mapping[(ref_type, pk)] = doc_date
    return mapping


def location_scope_label(location_id: int | None) -> str:
    if not location_id:
        return 'Toàn bộ kho'
    loc = source_locations_qs().filter(pk=location_id).first()
    return loc.display_label() if loc else 'Toàn bộ kho'


def report_xuat_nhap_ton(
    date_from: date,
    date_to: date,
    *,
    location_id: int | None = None,
    search: str = '',
    limit: int | None = DISPLAY_LIMIT,
) -> dict:
    """Tồn đầu kỳ + nhập − xuất = tồn cuối kỳ, theo ngày chứng từ và giá tồn thật."""
    qs = _ledger_qs(location_id)
    doc_dates = _doc_dates_for(qs)
    tz = timezone.get_current_timezone()

    materials = Material.objects.select_related('unit', 'category')
    search = (search or '').strip()
    moved_ids = set(qs.values_list('material_id', flat=True).distinct())
    if search:
        materials = apply_material_search(materials, search)
    else:
        materials = materials.filter(Q(is_active=True) | Q(pk__in=moved_ids))
    materials = list(materials.order_by('variant_group', 'code'))
    material_by_id = {m.pk: m for m in materials}

    buckets: dict[int, dict] = defaultdict(_zero_bucket)
    for entry in qs.values(
        'material_id', 'qty_delta', 'amount', 'unit_price',
        'ref_type', 'ref_id', 'created_at',
    ):
        material = material_by_id.get(entry['material_id'])
        if material is None and search:
            continue
        txn_date = doc_dates.get((entry['ref_type'], entry['ref_id']))
        if txn_date is None:
            created = entry['created_at']
            if timezone.is_aware(created):
                created = timezone.localtime(created, tz)
            txn_date = created.date()
        if txn_date > date_to:
            continue
        qty = entry['qty_delta'] or Decimal('0')
        base_price = material.base_price if material is not None else Decimal('0')
        amount = _line_amount(qty, entry['amount'] or Decimal('0'), entry['unit_price'] or Decimal('0'), base_price)
        bucket = buckets[entry['material_id']]
        if txn_date < date_from:
            bucket['qty_open'] += qty
            bucket['val_open'] += amount if qty >= 0 else -amount
            continue
        if qty > 0:
            bucket['qty_in'] += qty
            bucket['val_in'] += amount
        elif qty < 0:
            bucket['qty_out'] += -qty
            bucket['val_out'] += amount

    use_live_value = date_to >= timezone.localdate()
    live_by_id = {}
    if use_live_value and materials:
        live_by_id = {
            row['material'].pk: row
            for row in material_stock_rows(Material.objects.filter(pk__in=[m.pk for m in materials]))
        }

    all_rows = []
    totals = _zero_totals()
    extra_ids = [mid for mid in buckets if mid not in material_by_id]
    if extra_ids:
        for mat in Material.objects.select_related('unit', 'category').filter(pk__in=extra_ids):
            materials.append(mat)
            material_by_id[mat.pk] = mat
        materials.sort(key=lambda m: ((m.variant_group or ''), m.code or ''))

    for material in materials:
        bucket = buckets.get(material.pk) or _zero_bucket()
        qty_open = bucket['qty_open']
        qty_in = bucket['qty_in']
        qty_out = bucket['qty_out']
        qty_close = qty_open + qty_in - qty_out
        val_in = bucket['val_in']
        val_out = bucket['val_out']
        live = live_by_id.get(material.pk)
        if live is not None:
            val_close = live.get('stock_value') or Decimal('0')
            val_open = val_close - val_in + val_out
        else:
            val_open = bucket['val_open']
            val_close = val_open + val_in - val_out
        row = {
            'material': material,
            'group_name': (material.variant_group or '').strip(),
            'code': material.code,
            'name': material.name,
            'qty_open': qty_open,
            'val_open': val_open,
            'qty_in': qty_in,
            'val_in': val_in,
            'qty_out': qty_out,
            'val_out': val_out,
            'qty_close': qty_close,
            'val_close': val_close,
        }
        _add_totals(totals, row)
        all_rows.append(row)

    all_groups = group_xnt_rows(all_rows)
    all_groups.sort(key=lambda g: (-(g.get('qty_close') or Decimal('0')), (g.get('group_name') or '').lower()))
    sku_count = len(all_rows)
    group_count = len(all_groups)
    if limit is None or limit <= 0:
        groups = all_groups
    else:
        groups = all_groups[:limit]
    return {
        'groups': groups,
        'all_rows': all_rows,
        'totals': totals,
        'total_count': group_count,
        'sku_count': sku_count,
        'displayed_count': len(groups),
        'truncated': group_count > len(groups),
        'display_limit': DISPLAY_LIMIT if limit is None else limit,
    }


def report_xuat_nhap_ton_export_rows(
    date_from: date,
    date_to: date,
    *,
    location_id: int | None = None,
    search: str = '',
) -> list[dict]:
    data = report_xuat_nhap_ton(
        date_from,
        date_to,
        location_id=location_id,
        search=search,
        limit=None,
    )
    export_rows = []
    for row in data['all_rows']:
        export_rows.append({
            label: row[key]
            for key, label in XNT_COLUMNS
        })
    totals = data['totals']
    if export_rows:
        export_rows.append({
            'Tên nhóm hàng': '',
            'Mã hàng': '',
            'Tên hàng': 'Tổng cộng',
            **{label: totals[key] for key, label in XNT_COLUMNS if key not in ('group_name', 'code', 'name')},
        })
    return export_rows
