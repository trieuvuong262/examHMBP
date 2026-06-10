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


def material_total_qty(material: Material) -> Decimal:
    total = material.balances.aggregate(total=Sum('quantity'))['total']
    return total or Decimal('0')


def stock_status_for_qty(quantity: Decimal, min_stock: Decimal) -> str:
    qty = quantity or Decimal('0')
    minimum = min_stock or Decimal('0')
    if qty <= 0:
        return STOCK_STATUS_OUT
    if qty <= minimum:
        return STOCK_STATUS_LOW
    return STOCK_STATUS_OK


def material_stock_rows(queryset=None):
    """Tổng hợp tồn theo NPL — dùng cho tổng quan và danh sách tồn."""
    qs = queryset or Material.objects.filter(is_active=True).select_related(
        'category', 'unit', 'supplier',
    ).prefetch_related('balances__location')
    rows = []
    for material in qs:
        total = material_total_qty(material)
        primary_location = ''
        balances = list(material.balances.all())
        if balances:
            top = max(balances, key=lambda b: b.quantity)
            if top.quantity > 0:
                primary_location = top.location.code
        status = stock_status_for_qty(total, material.min_stock)
        rows.append({
            'material': material,
            'total_qty': total,
            'status': status,
            'status_label': STOCK_STATUS_LABELS[status],
            'status_badge': STOCK_STATUS_BADGE[status],
            'primary_location': primary_location,
        })
    return rows


def overview_stats():
    rows = material_stock_rows()
    total_materials = len(rows)
    low_count = sum(1 for r in rows if r['status'] == STOCK_STATUS_LOW)
    out_count = sum(1 for r in rows if r['status'] == STOCK_STATUS_OUT)
    ok_count = sum(1 for r in rows if r['status'] == STOCK_STATUS_OK)
    return {
        'total_materials': total_materials,
        'ok_count': ok_count,
        'low_count': low_count,
        'out_count': out_count,
        'alert_rows': [r for r in rows if r['status'] in (STOCK_STATUS_LOW, STOCK_STATUS_OUT)],
    }
