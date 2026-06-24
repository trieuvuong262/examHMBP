"""Logic báo cáo sản lượng hàng giờ — sản xuất."""

from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.db.models import Q
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
    slot_count_for_shift,
    slots_for_shift,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION


from reports.report_lock import (
    is_report_edit_expired,
    is_report_locked,
    lock_report_on_supervisor_view,
    report_edit_denied_message,
)


def is_production_report_locked(report) -> bool:
    """Khóa chỉnh sửa sau khi tổ trưởng / trưởng BP / trưởng phòng đã xem báo cáo."""
    return is_report_locked(report)


def lock_production_report_on_supervisor_view(report, viewer) -> bool:
    """Tự khóa khi cấp trên mở xem báo cáo đã gửi (lần đầu)."""
    return lock_report_on_supervisor_view(report, viewer)


def can_edit_production_norms(viewer, report) -> bool:
    """Quản lý xem báo cáo cấp dưới — được chỉnh định mức nếu nhân viên nhập sai."""
    if report.employee_id == viewer.id:
        return False
    from hrm.permissions import can_view_user_report
    return can_view_user_report(viewer, report)


def can_edit_production_report(viewer, report, *, can_submit, is_proxy=False) -> bool:
    if is_production_report_locked(report) or is_report_edit_expired(report):
        return False
    if report.employee_id == viewer.id:
        return can_submit
    if is_proxy:
        return can_proxy_enter_daily_report(viewer, report.employee)
    return False


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
        if not report.shift:
            raise ValueError('Báo cáo sản xuất cần chọn ca trước khi bắt đầu.')
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


def _entry_is_filled(entry: ProductionHourlyQuantity) -> bool:
    if not entry:
        return False
    if entry.quantity > 0:
        return True
    return bool((entry.zero_reason or '').strip())


def _last_filled_slot_index(product: ProductionShiftProduct) -> Optional[int]:
    filled = [
        e.slot_index
        for e in product.hourly_entries.all()
        if _entry_is_filled(e)
    ]
    return max(filled) if filled else None


def _shift_for_report(report: DailyWorkReport) -> str:
    return report.shift or DailyWorkReport.SHIFT_MORNING


def _shift_for_product(product: ProductionShiftProduct) -> str:
    return _shift_for_report(product.report)


def compute_first_slot_index(
    report: DailyWorkReport,
    after_product: Optional[ProductionShiftProduct] = None,
) -> int:
    """Khung giờ đầu tiên được phép nhập cho phiên mã hàng mới."""
    slot_count = slot_count_for_shift(_shift_for_report(report))
    if after_product is None:
        return 0
    last_filled = _last_filled_slot_index(after_product)
    if last_filled is None:
        return 0
    start = int(last_filled) + 1
    if start >= slot_count:
        return slot_count - 1
    return start


@transaction.atomic
def ensure_active_work_block(
    report: DailyWorkReport,
    *,
    after_product: Optional[ProductionShiftProduct] = None,
) -> ProductionShiftProduct:
    active = active_product(report)
    if active:
        return active
    sort_order = report.production_products.count()
    first_slot = compute_first_slot_index(report, after_product=after_product)
    return ProductionShiftProduct.objects.create(
        report=report,
        product_code='',
        process_name='',
        norm_per_hour=None,
        sort_order=sort_order,
        first_slot_index=first_slot,
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
    ensure_active_work_block(report, after_product=active)
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
    zero_reason=None,
    damaged_quantity=None,
    note=None,
    *,
    relax_slot_scope: bool = False,
) -> ProductionHourlyQuantity:
    shift = _shift_for_product(product)
    slot_count = slot_count_for_shift(shift)
    if slot_index < 0 or slot_index >= slot_count:
        raise ValueError('slot_index không hợp lệ')
    if not relax_slot_scope and slot_index < product.first_slot_index:
        raise ValueError('Khung giờ này không thuộc phiên mã hàng hiện tại.')
    qty = max(0, int(quantity))
    reason = (zero_reason or '').strip()
    if qty == 0 and not reason:
        raise ValueError('Cần nhập lý do khi sản lượng bằng 0.')
    partial = None
    if partial_hours not in (None, ''):
        partial = Decimal(str(partial_hours))
    defaults = {
        'quantity': qty,
        'partial_hours': partial,
        'zero_reason': '' if qty > 0 else reason[:200],
    }
    if damaged_quantity is not None:
        defaults['damaged_quantity'] = max(0, int(damaged_quantity)) if qty > 0 else 0
    if note is not None:
        defaults['note'] = (note or '').strip()[:500]
    entry, _ = ProductionHourlyQuantity.objects.update_or_create(
        product=product,
        slot_index=slot_index,
        defaults=defaults,
    )
    return entry


def cumulative_quantity(product: ProductionShiftProduct, up_to_slot: int) -> int:
    total = 0
    for entry in product.hourly_entries.filter(slot_index__lte=up_to_slot).order_by('slot_index'):
        total += entry.quantity
    return total


def product_slot_cell(product: ProductionShiftProduct, slot_index: int) -> dict:
    shift = _shift_for_product(product)
    if slot_index < product.first_slot_index:
        slot = slot_by_index(slot_index, shift)
        return {
            'slot_index': slot_index,
            'slot_label': slot.label if slot else str(slot_index),
            'quantity': 0,
            'cumulative': 0,
            'partial_hours': None,
            'display': '',
            'has_data': False,
            'is_na': True,
            'zero_reason': '',
            'damaged_quantity': 0,
            'note': '',
            'entry_id': None,
        }
    entry = product.hourly_entries.filter(slot_index=slot_index).first()
    qty = entry.quantity if entry else 0
    reason = (entry.zero_reason or '').strip() if entry else ''
    damaged = entry.damaged_quantity if entry else 0
    entry_note = (entry.note or '').strip() if entry else ''
    filled = _entry_is_filled(entry)
    cum = cumulative_quantity(product, slot_index) if qty else 0
    partial = entry.partial_hours if entry else None
    display = ''
    if entry and filled:
        if qty > 0:
            if partial:
                display = f'{qty}/{partial}h'
            else:
                display = str(qty)
        else:
            display = '0'
    slot = slot_by_index(slot_index, shift)
    return {
        'slot_index': slot_index,
        'slot_label': slot.label if slot else str(slot_index),
        'quantity': qty,
        'cumulative': cum if qty else 0,
        'partial_hours': partial,
        'display': display,
        'has_data': filled,
        'is_na': False,
        'zero_reason': reason,
        'damaged_quantity': damaged,
        'note': entry_note,
        'entry_id': entry.pk if entry else None,
    }


def _product_has_hourly_data(product: ProductionShiftProduct) -> bool:
    return product.hourly_entries.filter(quantity__gt=0).exists()


def build_productivity_report(report: DailyWorkReport) -> dict:
    """Báo cáo năng suất theo từng khung giờ — dành cho quản lý xem."""
    shift = _shift_for_report(report)
    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    product_order = {product.id: index for index, product in enumerate(products)}
    hourly_rows = []
    product_summaries = []
    total_qty = 0
    total_hours = Decimal('0')
    total_expected = Decimal('0')

    for product in products:
        code = (product.product_code or '').strip() or '—'
        process = (product.process_name or '').strip() or 'Chưa gắn mã'
        norm = product.norm_per_hour
        prod_qty = 0
        prod_hours = Decimal('0')
        prod_expected = Decimal('0')

        for entry in product.hourly_entries.order_by('slot_index'):
            if not _entry_is_filled(entry):
                continue
            if entry.slot_index < product.first_slot_index:
                continue

            slot = slot_by_index(entry.slot_index, shift)
            hours = entry.partial_hours if entry.partial_hours is not None else Decimal('1')
            qty = entry.quantity
            efficiency_pct = None

            if qty > 0 and norm and norm > 0:
                expected = norm * hours
                efficiency_pct = float(
                    (Decimal(qty) / expected * 100).quantize(Decimal('0.01'))
                )
                prod_qty += qty
                prod_hours += hours
                prod_expected += expected
                total_qty += qty
                total_hours += hours
                total_expected += expected

            hourly_rows.append({
                'product_id': product.id,
                'slot_index': entry.slot_index,
                'slot_label': slot.label if slot else str(entry.slot_index),
                'product_code': code,
                'process_name': process,
                'quantity': qty,
                'norm_per_hour': float(norm) if norm is not None else None,
                'hours': float(hours),
                'hours_display': _format_hours(hours),
                'efficiency_pct': efficiency_pct,
                'zero_reason': (entry.zero_reason or '').strip(),
                'damaged_quantity': entry.damaged_quantity,
                'note': (entry.note or '').strip(),
                'is_unfinalized': not (product.product_code or '').strip(),
            })

        if prod_qty > 0 and norm and norm > 0:
            product_summaries.append({
                'product_id': product.id,
                'product_code': code,
                'process_name': process,
                'quantity': prod_qty,
                'norm_per_hour': float(norm),
                'hours': float(prod_hours),
                'hours_display': _format_hours(prod_hours),
                'efficiency_pct': float(
                    (Decimal(prod_qty) / prod_expected * 100).quantize(Decimal('0.01'))
                ),
            })

    hourly_rows.sort(
        key=lambda row: (product_order.get(row['product_id'], 999), row['slot_index'])
    )

    overall_efficiency_pct = None
    if total_expected > 0:
        overall_efficiency_pct = float(
            (Decimal(total_qty) / total_expected * 100).quantize(Decimal('0.01'))
        )

    profile = getattr(report.employee, 'profile', None)
    department_name = profile.department.name if profile and profile.department_id else '—'
    employee_name = (profile.full_name if profile and profile.full_name else report.employee.username)

    return {
        'hourly_rows': hourly_rows,
        'product_summaries': product_summaries,
        'summary_product_ids': [summary['product_id'] for summary in product_summaries],
        'total_quantity': total_qty,
        'total_hours': float(total_hours),
        'total_hours_display': _format_hours(total_hours),
        'overall_efficiency_pct': overall_efficiency_pct,
        'employee_name': employee_name,
        'department_name': department_name,
        'report_date': report.report_date,
        'has_data': bool(hourly_rows),
    }


def update_product_norms(report: DailyWorkReport, norms_by_id: dict) -> int:
    """Quản lý chỉnh định mức theo mã hàng — cập nhật ProductionShiftProduct."""
    if not norms_by_id:
        return 0
    products = {product.id: product for product in report.production_products.all()}
    updated = 0
    for product_id, norm in norms_by_id.items():
        product = products.get(int(product_id))
        if not product or norm is None or norm <= 0:
            continue
        product.norm_per_hour = Decimal(str(norm))
        product.save(update_fields=['norm_per_hour'])
        updated += 1
    return updated


def _format_hours(value) -> str:
    dec = Decimal(str(value)).normalize()
    text = format(dec, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return f'{text}h'


def build_hourly_grid(report: DailyWorkReport) -> dict:
    """Bảng tổng — gồm mã đã kết thúc và phiên đang nhập (chưa gắn mã hàng)."""
    shift = _shift_for_report(report)
    slot_count = slot_count_for_shift(shift)
    hourly_slots = slots_for_shift(shift)
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
        slots = [product_slot_cell(product, i) for i in range(slot_count)]
        total_qty = sum(cell['quantity'] for cell in slots)
        rows.append({
            'id': product.pk,
            'product_code': product.product_code.strip() if product.product_code else '',
            'process_name': product.process_name.strip() if product.process_name else '',
            'norm_per_hour': float(product.norm_per_hour) if product.norm_per_hour is not None else None,
            'status': product.status,
            'is_unfinalized': is_unfinalized,
            'first_slot_index': product.first_slot_index,
            'label_code': product.product_code.strip() if product.product_code else '—',
            'label_process': product.process_name.strip() if product.process_name else 'Chưa gắn mã',
            'slots': slots,
            'total_quantity': total_qty,
        })
    return {
        'slots': [{'index': s.index, 'label': s.label} for s in hourly_slots],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
        'has_unfinalized': any(r['is_unfinalized'] for r in rows),
        'shift': shift,
    }


def product_slot_cell_proxy(product: ProductionShiftProduct, slot_index: int) -> dict:
    """Ô lưới nhập hộ — mọi khung giờ đều nhập được, không ràng buộc thời gian."""
    shift = _shift_for_product(product)
    entry = product.hourly_entries.filter(slot_index=slot_index).first()
    qty = entry.quantity if entry else 0
    reason = (entry.zero_reason or '').strip() if entry else ''
    damaged = entry.damaged_quantity if entry else 0
    entry_note = (entry.note or '').strip() if entry else ''
    filled = _entry_is_filled(entry)
    cum = cumulative_quantity(product, slot_index) if qty else 0
    partial = entry.partial_hours if entry else None
    display = ''
    if entry and filled:
        if qty > 0:
            display = f'{qty}/{partial}h' if partial else str(qty)
        else:
            display = '0'
    slot = slot_by_index(slot_index, shift)
    return {
        'slot_index': slot_index,
        'slot_label': slot.label if slot else str(slot_index),
        'quantity': qty,
        'cumulative': cum if qty else 0,
        'partial_hours': partial,
        'display': display,
        'has_data': True,
        'is_na': False,
        'zero_reason': reason,
        'damaged_quantity': damaged,
        'note': entry_note,
        'entry_id': entry.pk if entry else None,
    }


def build_proxy_entry_grid(report: DailyWorkReport) -> dict:
    """Bảng nhập hộ — tổ trưởng điền sản lượng công nhân, không theo giờ thực."""
    shift = _shift_for_report(report)
    slot_count = slot_count_for_shift(shift)
    hourly_slots = slots_for_shift(shift)
    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    rows = []
    for product in products:
        is_active = product.status == ProductionShiftProduct.STATUS_ACTIVE
        has_data = _product_has_hourly_data(product)
        if not has_data and not is_active:
            continue
        is_unfinalized = (
            is_active
            or not (product.product_code or '').strip()
        )
        slots = [product_slot_cell_proxy(product, i) for i in range(slot_count)]
        total_qty = sum(cell['quantity'] for cell in slots)
        rows.append({
            'id': product.pk,
            'product_code': product.product_code.strip() if product.product_code else '',
            'process_name': product.process_name.strip() if product.process_name else '',
            'norm_per_hour': float(product.norm_per_hour) if product.norm_per_hour is not None else None,
            'status': product.status,
            'is_unfinalized': is_unfinalized,
            'first_slot_index': 0,
            'label_code': product.product_code.strip() if product.product_code else '—',
            'label_process': product.process_name.strip() if product.process_name else 'Chưa gắn mã',
            'slots': slots,
            'total_quantity': total_qty,
        })
    return {
        'slots': [{'index': s.index, 'label': s.label} for s in hourly_slots],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
        'has_unfinalized': any(r['is_unfinalized'] for r in rows),
        'proxy_mode': True,
        'shift': shift,
    }


def pending_slots_for_report(
    report: DailyWorkReport,
    now=None,
    *,
    ignore_time_constraints: bool = False,
) -> list[dict]:
    """Slot chưa nhập cho phiên đang làm (chỉ từ khung bắt đầu phiên trở đi)."""
    product = active_product(report)
    if not product:
        return []
    shift = _shift_for_report(report)
    slot_count = slot_count_for_shift(shift)
    if ignore_time_constraints:
        due = list(range(slot_count))
    else:
        due = due_slot_indices(now, report.report_date, shift)
        if not due:
            return []
    filled = set(
        product.hourly_entries.filter(
            slot_index__gte=product.first_slot_index,
        ).filter(
            Q(quantity__gt=0) | ~Q(zero_reason=''),
        ).values_list('slot_index', flat=True)
    )
    pending = []
    start = 0 if ignore_time_constraints else product.first_slot_index
    for idx in due:
        if idx < start:
            continue
        if idx in filled:
            continue
        slot = slot_by_index(idx, shift)
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
