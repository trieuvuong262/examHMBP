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


def can_edit_production_report(viewer, report, *, can_submit, is_proxy=False) -> bool:
    if report.employee_id == viewer.id:
        return can_submit
    if is_proxy:
        return can_proxy_enter_daily_report(viewer, report.employee)
    from hrm.permissions import can_review_user_report
    return can_review_user_report(viewer, report)


def can_proxy_enter_daily_report(viewer, employee) -> bool:
    """Tổ trưởng / cấp trên nhập báo cáo hộ nhân viên (điện thoại hỏng)."""
    from hrm.permissions import can_view_team_reports, get_report_team_users
    if not can_view_team_reports(viewer):
        return False
    return get_report_team_users(viewer).filter(pk=employee.pk).exists()


@transaction.atomic
def ensure_work_day_started(report: DailyWorkReport) -> DailyWorkReport:
    """Tự bắt đầu ngày làm khi vào trang — không chọn ca."""
    if not report.shift_started_at:
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.shift = ''
        report.shift_started_at = timezone.now()
        report.status = DailyWorkReport.STATUS_DRAFT
        report.draft_saved_at = timezone.now()
        report.save()
    ensure_active_work_block(report)
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
def ensure_active_work_block(report: DailyWorkReport) -> ProductionShiftProduct:
    active = active_product(report)
    if active:
        return active
    sort_order = report.production_products.count()
    return ProductionShiftProduct.objects.create(
        report=report,
        product_code='',
        process_name='',
        norm_per_hour=None,
        sort_order=sort_order,
        status=ProductionShiftProduct.STATUS_ACTIVE,
    )


def active_has_hourly_data(product: ProductionShiftProduct) -> bool:
    return product.hourly_entries.filter(quantity__gt=0).exists()


@transaction.atomic
def finalize_product_with_metadata(
    report: DailyWorkReport,
    *,
    product_code: str,
    process_name: str,
    norm_per_hour,
) -> Optional[ProductionShiftProduct]:
    """Kết thúc mã hàng — gắn thông tin sau khi đã nhập sản lượng từng giờ."""
    active = active_product(report)
    if not active:
        return None
    if not active_has_hourly_data(active):
        return None
    active.product_code = product_code.strip()
    active.process_name = process_name.strip()
    active.norm_per_hour = Decimal(str(norm_per_hour))
    active.status = ProductionShiftProduct.STATUS_DONE
    active.ended_at = timezone.now()
    active.save()
    ensure_active_work_block(report)
    return active


def unfinalized_active_with_data(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    active = active_product(report)
    if active and active_has_hourly_data(active):
        return active
    return None


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


def _product_has_hourly_data(product: ProductionShiftProduct) -> bool:
    return product.hourly_entries.filter(quantity__gt=0).exists()


def build_hourly_grid(report: DailyWorkReport) -> dict:
    """Bảng tổng — gồm mã đã kết thúc và phiên đang nhập (chưa gắn mã hàng)."""
    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    rows = []
    for product in products:
        if not _product_has_hourly_data(product):
            continue
        is_unfinalized = (
            product.status == ProductionShiftProduct.STATUS_ACTIVE
            or not (product.product_code or '').strip()
        )
        slots = [product_slot_cell(product, i) for i in range(SLOT_COUNT)]
        total_qty = sum(cell['quantity'] for cell in slots)
        rows.append({
            'id': product.pk,
            'product_code': product.product_code.strip() if product.product_code else '',
            'process_name': product.process_name.strip() if product.process_name else '',
            'norm_per_hour': float(product.norm_per_hour) if product.norm_per_hour is not None else None,
            'status': product.status,
            'is_unfinalized': is_unfinalized,
            'label_code': product.product_code.strip() if product.product_code else '—',
            'label_process': product.process_name.strip() if product.process_name else 'Chưa gắn mã',
            'slots': slots,
            'total_quantity': total_qty,
        })
    return {
        'slots': [{'index': s.index, 'label': s.label} for s in PRODUCTION_HOURLY_SLOTS],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
        'has_unfinalized': any(r['is_unfinalized'] for r in rows),
    }


def pending_slots_for_report(report: DailyWorkReport, now=None) -> list[dict]:
    """Slot chưa nhập cho phiên đang làm (chỉ các giờ đã qua)."""
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
