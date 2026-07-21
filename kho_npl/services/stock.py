from decimal import Decimal

from django.db.models import Sum

from kho_npl.choices import (
    STOCK_STATUS_BADGE,
    STOCK_STATUS_LABELS,
    STOCK_STATUS_LOW,
    STOCK_STATUS_OK,
    STOCK_STATUS_OUT,
)
from kho_npl.models import Material, StockBalance
from kho_npl.material_search import apply_smart_search
from kho_npl.services.batches import material_batch_totals
from kho_npl.services.scrap_warehouse import exclude_scrap_locations


def material_total_qty(material: Material) -> Decimal:
    total = exclude_scrap_locations(
        StockBalance.objects.filter(material=material),
    ).aggregate(total=Sum('quantity'))['total']
    return total or Decimal('0')


def sync_balances_from_ledger(material: Material | None = None) -> int:
    """Đồng bộ bảng tồn kho từ tổng biến động sổ theo từng NPL × vị trí."""
    from kho_npl.models import StockLedger

    ledger_qs = StockLedger.objects.all()
    balance_qs = StockBalance.objects.all()
    if material is not None:
        ledger_qs = ledger_qs.filter(material=material)
        balance_qs = balance_qs.filter(material=material)

    updated = 0
    seen: set[tuple[int, int]] = set()
    pairs = ledger_qs.values('material_id', 'location_id').distinct()
    for pair in pairs:
        key = (pair['material_id'], pair['location_id'])
        if key in seen:
            continue
        seen.add(key)
        total = ledger_qs.filter(
            material_id=pair['material_id'],
            location_id=pair['location_id'],
        ).aggregate(total=Sum('qty_delta'))['total'] or Decimal('0')
        bal, _created = StockBalance.objects.update_or_create(
            material_id=pair['material_id'],
            location_id=pair['location_id'],
            defaults={'quantity': total},
        )
        if bal.quantity != total:
            bal.quantity = total
            bal.save(update_fields=['quantity', 'updated_at'])
            updated += 1

    for bal in balance_qs:
        key = (bal.material_id, bal.location_id)
        if key in seen:
            continue
        if bal.quantity != Decimal('0'):
            bal.quantity = Decimal('0')
            bal.save(update_fields=['quantity', 'updated_at'])
            updated += 1

    return updated


def stock_status_for_qty(quantity: Decimal, min_stock: Decimal) -> str:
    qty = quantity or Decimal('0')
    minimum = min_stock or Decimal('0')
    if qty <= 0:
        return STOCK_STATUS_OUT
    if qty <= minimum:
        return STOCK_STATUS_LOW
    return STOCK_STATUS_OK


def material_stock_rows(queryset=None, location_ids: list[int] | None = None):
    """Tổng hợp tồn theo NPL — dùng cho tổng quan và danh sách tồn."""
    from kho_npl.services.scrap_warehouse import source_locations_qs

    storage_ids = set(source_locations_qs().values_list('pk', flat=True))
    qs = queryset or Material.objects.filter(is_active=True).select_related(
        'category', 'unit', 'supplier', 'color', 'specification',
    ).prefetch_related('balances__location')
    loc_set = set(location_ids or []) & storage_ids if location_ids else storage_ids
    rows = []
    for material in qs:
        balances = [b for b in material.balances.all() if b.location_id in storage_ids]
        if loc_set != storage_ids:
            balances = [b for b in balances if b.location_id in loc_set]
        total = sum((b.quantity for b in balances), Decimal('0'))
        location_balances = sorted(
            [
                {
                    'location': b.location,
                    'quantity': b.quantity,
                }
                for b in balances
            ],
            key=lambda item: (item['location'].display_label() or '').lower(),
        )
        primary_location = ''
        if location_balances:
            top = max(location_balances, key=lambda item: item['quantity'])
            if top['quantity'] > 0:
                primary_location = top['location'].display_label()
            elif location_balances:
                primary_location = location_balances[0]['location'].display_label()
        can_expand = len(location_balances) >= 1
        status = stock_status_for_qty(total, material.min_stock)
        _batch_qty, stock_value, avg_unit_price = material_batch_totals(material)
        # Có tồn nhưng chưa có lô kèm giá — tạm tính giá trị tồn theo giá cơ bản
        if stock_value <= 0 and total > 0 and material.base_price:
            stock_value = (total * material.base_price).quantize(Decimal('0.01'))
        rows.append({
            'material': material,
            'total_qty': total,
            'avg_unit_price': avg_unit_price,
            'stock_value': stock_value,
            'status': status,
            'status_label': STOCK_STATUS_LABELS[status],
            'status_badge': STOCK_STATUS_BADGE[status],
            'primary_location': primary_location,
            'location_balances': location_balances,
            'can_expand': can_expand,
            'location_count': len(location_balances),
        })
    return rows


def stock_rows_for_status(rows, status: str | None = None):
    """Lọc dòng tồn theo trạng thái cảnh báo (low / out / cả hai)."""
    if status == STOCK_STATUS_LOW:
        return [r for r in rows if r['status'] == STOCK_STATUS_LOW]
    if status == STOCK_STATUS_OUT:
        return [r for r in rows if r['status'] == STOCK_STATUS_OUT]
    return [r for r in rows if r['status'] in (STOCK_STATUS_LOW, STOCK_STATUS_OUT)]


def balance_stock_rows(
    *,
    location_id=None,
    category_id=None,
    status_filter=None,
    search_query='',
    active_materials_only=True,
):
    """Tồn theo NPL × vị trí — màn Thẻ kho."""
    qs = exclude_scrap_locations(
        StockBalance.objects.select_related(
            'material__category',
            'material__unit',
            'material__supplier',
            'location',
        ),
    )
    if active_materials_only:
        qs = qs.filter(material__is_active=True)
    if location_id:
        qs = qs.filter(location_id=location_id)
    if category_id:
        qs = qs.filter(material__category_id=category_id)
    if search_query:
        qs = apply_smart_search(qs, search_query, ('material__name',))

    rows = []
    for balance in qs.order_by('location__code', 'material__code'):
        material = balance.material
        total = material_total_qty(material)
        status = stock_status_for_qty(total, material.min_stock)
        rows.append({
            'balance': balance,
            'material': material,
            'location': balance.location,
            'quantity': balance.quantity,
            'total_qty': total,
            'status': status,
            'status_label': STOCK_STATUS_LABELS[status],
            'status_badge': STOCK_STATUS_BADGE[status],
        })

    if status_filter:
        rows = [r for r in rows if r['status'] == status_filter]
    return rows
