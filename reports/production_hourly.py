"""Logic báo cáo sản lượng hàng giờ — sản xuất."""

from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.utils import timezone

from reports.models import (
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
)
from reports.production_slots import (
    PRODUCTION_HOURLY_SLOTS,
    SLOT_COUNT,
    current_slot_index,
    due_slot_indices,
    slot_by_index,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION


def can_edit_production_report(viewer, report, *, can_submit, can_review) -> bool:
    if report.employee_id == viewer.id:
        return can_submit
    return can_review


@transaction.atomic
def start_production_shift(report: DailyWorkReport, shift: str) -> DailyWorkReport:
    report.report_profile = REPORT_PROFILE_PRODUCTION
    report.shift = shift
    report.shift_started_at = timezone.now()
    report.status = DailyWorkReport.STATUS_DRAFT
    report.draft_saved_at = timezone.now()
    report.save()
    return report


def active_product(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    if not report.pk:
        return None
    return (
        report.production_products.filter(status=ProductionShiftProduct.STATUS_ACTIVE)
        .order_by('-sort_order', '-id')
        .first()
    )


@transaction.atomic
def start_product_session(
    report: DailyWorkReport,
    *,
    product_code: str,
    process_name: str,
    norm_per_hour,
) -> ProductionShiftProduct:
    active = active_product(report)
    if active:
        active.status = ProductionShiftProduct.STATUS_DONE
        active.ended_at = timezone.now()
        active.save(update_fields=['status', 'ended_at'])
    sort_order = report.production_products.count()
    return ProductionShiftProduct.objects.create(
        report=report,
        product_code=product_code.strip(),
        process_name=process_name.strip(),
        norm_per_hour=Decimal(str(norm_per_hour)),
        sort_order=sort_order,
        status=ProductionShiftProduct.STATUS_ACTIVE,
    )


@transaction.atomic
def end_active_product(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    active = active_product(report)
    if not active:
        return None
    active.status = ProductionShiftProduct.STATUS_DONE
    active.ended_at = timezone.now()
    active.save(update_fields=['status', 'ended_at'])
    return active


def save_hourly_entry(
    product: ProductionShiftProduct,
    slot_index: int,
    quantity: int,
    partial_hours=None,
) -> ProductionHourlyQuantity:
    if slot_index < 0 or slot_index >= SLOT_COUNT:
        raise ValueError('slot_index không hợp lệ')
    partial = None
    if partial_hours not in (None, ''):
        partial = Decimal(str(partial_hours))
    entry, _ = ProductionHourlyQuantity.objects.update_or_create(
        product=product,
        slot_index=slot_index,
        defaults={
            'quantity': max(0, int(quantity)),
            'partial_hours': partial,
        },
    )
    return entry


def cumulative_quantity(product: ProductionShiftProduct, up_to_slot: int) -> int:
    total = 0
    for entry in product.hourly_entries.filter(slot_index__lte=up_to_slot).order_by('slot_index'):
        total += entry.quantity
    return total


def product_slot_cell(product: ProductionShiftProduct, slot_index: int) -> dict:
    entry = product.hourly_entries.filter(slot_index=slot_index).first()
    qty = entry.quantity if entry else 0
    cum = cumulative_quantity(product, slot_index) if qty else 0
    partial = entry.partial_hours if entry else None
    display = ''
    if entry and qty:
        if partial:
            display = f'{qty}/{partial}h'
        else:
            display = str(qty)
    return {
        'slot_index': slot_index,
        'quantity': qty,
        'cumulative': cum if qty else 0,
        'partial_hours': partial,
        'display': display,
        'has_data': bool(entry and qty),
        'entry_id': entry.pk if entry else None,
    }


def build_hourly_grid(report: DailyWorkReport) -> dict:
    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    rows = []
    for product in products:
        slots = [product_slot_cell(product, i) for i in range(SLOT_COUNT)]
        total_qty = cumulative_quantity(product, SLOT_COUNT - 1)
        rows.append({
            'id': product.pk,
            'product_code': product.product_code,
            'process_name': product.process_name,
            'norm_per_hour': float(product.norm_per_hour),
            'status': product.status,
            'slots': slots,
            'total_quantity': total_qty,
        })
    return {
        'slots': [{'index': s.index, 'label': s.label} for s in PRODUCTION_HOURLY_SLOTS],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
    }


def pending_slots_for_report(report: DailyWorkReport, now=None) -> list[dict]:
    """Slot chưa nhập cho mã hàng đang làm (chỉ các giờ đã qua)."""
    product = active_product(report)
    if not product:
        return []
    due = due_slot_indices(now, report.report_date)
    if not due:
        return []
    filled = set(product.hourly_entries.filter(quantity__gt=0).values_list('slot_index', flat=True))
    pending = []
    for idx in due:
        if idx in filled:
            continue
        slot = slot_by_index(idx)
        pending.append({
            'slot_index': idx,
            'label': slot.label if slot else str(idx),
        })
    return pending


def shift_is_started(report: DailyWorkReport) -> bool:
    return bool(report.shift_started_at)


def parse_decimal(value, default=None):
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return default


def parse_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
