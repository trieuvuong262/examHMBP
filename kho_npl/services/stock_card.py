"""Thẻ kho — sổ biến động từng NPL (khớp StockLedger)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from kho_npl.models import Material, StockBalance, StockLedger, WarehouseLocation
from kho_npl.services.stock import material_total_qty

REF_LABELS = {
    StockLedger.REF_RECEIPT: 'Nhập kho',
    StockLedger.REF_ISSUE: 'Xuất kho',
    StockLedger.REF_ADJUSTMENT: 'Điều chỉnh',
    StockLedger.REF_STOCKTAKE: 'Kiểm kê',
    StockLedger.REF_TRANSFER: 'Chuyển kho',
    StockLedger.REF_DISPOSAL: 'Phiếu hủy',
}


def _apply_location_filter(qs, location_id: int | None = None, location_ids: list[int] | None = None):
    if location_ids:
        return qs.filter(location_id__in=location_ids)
    if location_id:
        return qs.filter(location_id=location_id)
    return qs


def _ledger_qs(
    material: Material,
    location_id: int | None = None,
    location_ids: list[int] | None = None,
):
    qs = StockLedger.objects.filter(material=material).select_related('location', 'created_by')
    qs = _apply_location_filter(qs, location_id, location_ids)
    return qs.order_by('created_at', 'id')


def ledger_delta_total(
    material: Material,
    location_id: int | None = None,
    location_ids: list[int] | None = None,
) -> Decimal:
    qs = _apply_location_filter(
        StockLedger.objects.filter(material=material),
        location_id,
        location_ids,
    )
    total = qs.aggregate(total=Sum('qty_delta'))['total']
    return total or Decimal('0')


def stock_balance_total(
    material: Material,
    location_id: int | None = None,
    location_ids: list[int] | None = None,
) -> Decimal:
    if location_ids:
        total = StockBalance.objects.filter(
            material=material,
            location_id__in=location_ids,
        ).aggregate(total=Sum('quantity'))['total']
        return total or Decimal('0')
    if location_id:
        bal = StockBalance.objects.filter(material=material, location_id=location_id).first()
        return bal.quantity if bal else Decimal('0')
    return material_total_qty(material)


def ledger_matches_stock(
    material: Material,
    location_id: int | None = None,
    location_ids: list[int] | None = None,
) -> bool:
    return ledger_delta_total(material, location_id, location_ids) == stock_balance_total(
        material, location_id, location_ids,
    )


def _scope_label(location_ids: list[int] | None, location_id: int | None) -> tuple[str, bool]:
    if location_ids:
        codes = list(
            WarehouseLocation.objects.filter(pk__in=location_ids)
            .order_by('code')
            .values_list('code', flat=True),
        )
        if len(codes) == 1:
            return codes[0], True
        if len(codes) <= 3:
            return ', '.join(codes), True
        return f'{len(codes)} kệ đã chọn', True
    if location_id:
        code = (
            WarehouseLocation.objects.filter(pk=location_id)
            .values_list('code', flat=True)
            .first()
        ) or 'Vị trí'
        return code, True
    return 'Tổng mọi kệ', False


def build_material_stock_card(
    material: Material,
    *,
    location_id: int | None = None,
    location_ids: list[int] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Dòng thẻ kho: tồn đầu kỳ + từng biến động (+nhập / -xuất) và tồn lũy kế."""
    if location_ids and location_id:
        location_id = None
    all_entries = list(_ledger_qs(material, location_id, location_ids))

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

    for entry in period_entries:
        balance_before = entry.balance_after - entry.qty_delta
        rows.append(_txn_row(entry, balance_before, entry.balance_after))

    totals_in = sum((r['qty_in'] for r in rows if r['kind'] == 'txn'), Decimal('0'))
    totals_out = sum((r['qty_out'] for r in rows if r['kind'] == 'txn'), Decimal('0'))

    system_stock = stock_balance_total(material, location_id, location_ids)
    ledger_total = ledger_delta_total(material, location_id, location_ids)
    variance = system_stock - ledger_total
    scope_label, scope_is_location = _scope_label(location_ids, location_id)

    if location_id and not location_ids:
        closing = period_entries[-1].balance_after if period_entries else opening
    elif location_ids and len(location_ids) == 1:
        closing = period_entries[-1].balance_after if period_entries else opening
    else:
        closing = ledger_total

    return {
        'rows': rows,
        'opening_balance': opening,
        'closing_balance': closing,
        'totals_in': totals_in,
        'totals_out': totals_out,
        'system_stock': system_stock,
        'ledger_total': ledger_total,
        'variance': variance,
        'is_consistent': ledger_matches_stock(material, location_id, location_ids),
        'period_entry_count': len(period_entries),
        'scope_label': scope_label,
        'scope_is_location': scope_is_location,
        'unit': material.unit,
    }


def diagnose_stock_mismatch(material: Material) -> dict:
    """So sánh tồn StockBalance vs tổng biến động sổ kho theo từng vị trí."""
    from kho_npl.models import WarehouseLocation

    total_balance = stock_balance_total(material, None)
    total_ledger = ledger_delta_total(material, None)
    location_rows = []

    ledger_loc_ids = set(
        StockLedger.objects.filter(material=material).values_list('location_id', flat=True).distinct(),
    )
    balance_loc_ids = set(
        StockBalance.objects.filter(material=material).exclude(quantity=0).values_list('location_id', flat=True),
    )
    loc_ids = ledger_loc_ids | balance_loc_ids

    locations = WarehouseLocation.objects.filter(id__in=loc_ids).order_by('code')
    for loc in locations:
        bal = StockBalance.objects.filter(material=material, location=loc).first()
        balance_qty = bal.quantity if bal else Decimal('0')
        ledger_sum = ledger_delta_total(material, loc.id)
        last_entry = (
            StockLedger.objects.filter(material=material, location=loc)
            .order_by('-created_at', '-id')
            .first()
        )
        last_balance = last_entry.balance_after if last_entry else Decimal('0')
        txn_count = StockLedger.objects.filter(material=material, location=loc).count()
        variance_ledger = balance_qty - ledger_sum
        variance_last = balance_qty - last_balance if last_entry else balance_qty
        is_ok = variance_ledger == 0 and (not last_entry or variance_last == 0)
        if balance_qty == 0 and ledger_sum == 0 and txn_count == 0:
            continue
        location_rows.append({
            'location_id': loc.id,
            'location_code': loc.code,
            'location_name': loc.name,
            'balance_qty': balance_qty,
            'ledger_sum': ledger_sum,
            'last_balance': last_balance,
            'txn_count': txn_count,
            'variance_ledger': variance_ledger,
            'variance_last': variance_last,
            'is_ok': is_ok,
        })

    location_rows.sort(key=lambda r: (0 if r['is_ok'] else 1, -abs(r['variance_ledger'])))

    problem_rows = [r for r in location_rows if not r['is_ok']]
    return {
        'total_balance': total_balance,
        'total_ledger': total_ledger,
        'total_variance': total_balance - total_ledger,
        'location_rows': location_rows,
        'problem_rows': problem_rows,
        'problem_count': len(problem_rows),
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
