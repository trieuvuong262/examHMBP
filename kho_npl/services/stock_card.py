"""Thẻ kho — sổ biến động từng NPL (khớp StockLedger)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from kho_npl.models import Material, StockBalance, StockLedger
from kho_npl.services.stock import material_total_qty

REF_LABELS = {
    StockLedger.REF_RECEIPT: 'Nhập kho',
    StockLedger.REF_ISSUE: 'Xuất kho',
    StockLedger.REF_ADJUSTMENT: 'Điều chỉnh',
    StockLedger.REF_STOCKTAKE: 'Kiểm kê',
    StockLedger.REF_TRANSFER: 'Chuyển kho',
    StockLedger.REF_DISPOSAL: 'Phiếu hủy',
}


def _ledger_qs(material: Material, location_id: int | None = None):
    qs = StockLedger.objects.filter(material=material).select_related('location', 'created_by')
    if location_id:
        qs = qs.filter(location_id=location_id)
    return qs.order_by('created_at', 'id')


def ledger_delta_total(material: Material, location_id: int | None = None) -> Decimal:
    qs = StockLedger.objects.filter(material=material)
    if location_id:
        qs = qs.filter(location_id=location_id)
    total = qs.aggregate(total=Sum('qty_delta'))['total']
    return total or Decimal('0')


def stock_balance_total(material: Material, location_id: int | None = None) -> Decimal:
    if location_id:
        bal = StockBalance.objects.filter(material=material, location_id=location_id).first()
        return bal.quantity if bal else Decimal('0')
    return material_total_qty(material)


def ledger_matches_stock(material: Material, location_id: int | None = None) -> bool:
    return ledger_delta_total(material, location_id) == stock_balance_total(material, location_id)


def build_material_stock_card(
    material: Material,
    *,
    location_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Dòng thẻ kho: tồn đầu kỳ + từng biến động (+nhập / -xuất) và tồn lũy kế."""
    all_entries = list(_ledger_qs(material, location_id))

    opening = Decimal('0')
    period_entries = []
    for entry in all_entries:
        entry_date = timezone.localtime(entry.created_at).date()
        if date_from and entry_date < date_from:
            opening += entry.qty_delta
            continue
        if date_to and entry_date > date_to:
            continue
        period_entries.append(entry)

    rows = []
    if date_from is not None:
        rows.append({
            'kind': 'opening',
            'txn_date': date_from,
            'ref_number': '',
            'ref_type': '',
            'ref_type_label': 'Tồn đầu kỳ',
            'location_code': '',
            'qty_in': Decimal('0'),
            'qty_out': Decimal('0'),
            'qty_delta': Decimal('0'),
            'balance_before': opening,
            'balance_after': opening,
            'notes': '',
            'ref_url': '',
        })

    if location_id:
        for entry in period_entries:
            balance_before = entry.balance_after - entry.qty_delta
            rows.append(_txn_row(entry, balance_before, entry.balance_after))
        closing = period_entries[-1].balance_after if period_entries else opening
    else:
        running = opening
        for entry in period_entries:
            balance_before = running
            running += entry.qty_delta
            rows.append(_txn_row(entry, balance_before, running))
        closing = running

    totals_in = sum((r['qty_in'] for r in rows if r['kind'] == 'txn'), Decimal('0'))
    totals_out = sum((r['qty_out'] for r in rows if r['kind'] == 'txn'), Decimal('0'))

    system_stock = stock_balance_total(material, location_id)
    ledger_total = ledger_delta_total(material, location_id)

    return {
        'rows': rows,
        'opening_balance': opening,
        'closing_balance': closing,
        'totals_in': totals_in,
        'totals_out': totals_out,
        'system_stock': system_stock,
        'ledger_total': ledger_total,
        'is_consistent': ledger_matches_stock(material, location_id),
        'period_entry_count': len(period_entries),
    }


def _txn_row(entry: StockLedger, balance_before: Decimal, balance_after: Decimal) -> dict:
    delta = entry.qty_delta
    return {
        'kind': 'txn',
        'txn_date': timezone.localtime(entry.created_at).date(),
        'txn_datetime': entry.created_at,
        'ref_number': entry.ref_number,
        'ref_type': entry.ref_type,
        'ref_type_label': REF_LABELS.get(entry.ref_type, entry.ref_type),
        'location_code': entry.location.code,
        'qty_in': delta if delta > 0 else Decimal('0'),
        'qty_out': abs(delta) if delta < 0 else Decimal('0'),
        'qty_delta': delta,
        'balance_before': balance_before,
        'balance_after': balance_after,
        'notes': entry.notes,
        'ref_url': _ref_url(entry),
    }


def _ref_url(entry: StockLedger) -> str:
    from django.urls import reverse

    try:
        if entry.ref_type == StockLedger.REF_RECEIPT:
            return reverse('kho_npl:receipt_detail', args=[entry.ref_id])
        if entry.ref_type == StockLedger.REF_ISSUE:
            return reverse('kho_npl:issue_detail', args=[entry.ref_id])
        if entry.ref_type == StockLedger.REF_ADJUSTMENT:
            return reverse('kho_npl:adjustment_detail', args=[entry.ref_id])
        if entry.ref_type == StockLedger.REF_STOCKTAKE:
            return reverse('kho_npl:stocktake_detail', args=[entry.ref_id])
        if entry.ref_type == StockLedger.REF_TRANSFER:
            return reverse('kho_npl:transfer_detail', args=[entry.ref_id])
        if entry.ref_type == StockLedger.REF_DISPOSAL:
            return reverse('kho_npl:disposal_detail', args=[entry.ref_id])
    except Exception:
        return ''
    return ''
