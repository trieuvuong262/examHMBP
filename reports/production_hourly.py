"""Logic báo cáo sản lượng hàng giờ — sản xuất."""

from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import json
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
    _shift_window,
    _slot_end_dt,
    _slot_start_dt,
    current_slot_index,
    due_slot_indices,
    normalize_shift,
    shift_break_intervals,
    shift_contains_datetime,
    slot_by_index,
    slot_count_for_shift,
    slot_grid_meta,
    slots_for_shift,
    slots_overlapping_interval,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION

# POST keys — không bao giờ tin thời gian từ client (điện thoại có thể chỉnh giờ).
CLIENT_SESSION_TIME_POST_KEYS = frozenset({
    'started_at',
    'ended_at',
    'client_time',
    'session_started_at',
    'session_ended_at',
    'device_time',
})


def production_server_now() -> datetime:
    """Thời điểm hiện tại trên VPS — mọi mốc bắt đầu/kết thúc công đoạn dùng hàm này."""
    return timezone.now()


def client_supplied_session_time(request) -> bool:
    """True nếu client gửi kèm thời gian — bị bỏ qua, chỉ ghi nhận giờ VPS."""
    if not request:
        return False
    post = getattr(request, 'POST', None)
    if not post:
        return False
    return any(post.get(key) for key in CLIENT_SESSION_TIME_POST_KEYS)


from reports.report_lock import (
    is_report_locked,
    production_edit_denied_message,
    production_employee_may_edit,
    production_manager_may_edit,
)


def is_production_report_locked(report) -> bool:
    """Khóa chỉnh sửa sau khi quản lý đã duyệt báo cáo."""
    return is_report_locked(report)


def is_production_entry_closed(report) -> bool:
    """Đã gửi báo cáo — không nhập thêm công đoạn cho đến khi «Nhập tiếp»."""
    return report.status == DailyWorkReport.STATUS_SUBMITTED


def lock_production_steps_on_submit(report: DailyWorkReport) -> int:
    """Chốt mọi công đoạn đã hoàn tất tại thời điểm gửi báo cáo."""
    if not report.pk:
        return 0
    return report.production_products.filter(
        status=ProductionShiftProduct.STATUS_DONE,
        submitted_locked=False,
    ).update(submitted_locked=True)


def product_is_submitted_locked(product: ProductionShiftProduct) -> bool:
    return bool(getattr(product, 'submitted_locked', False))


def lock_production_report_on_supervisor_view(report, viewer) -> bool:
    """SX không tự khóa khi cấp trên xem — chỉ khóa khi bấm Duyệt."""
    return False


def can_edit_production_norms(viewer, report) -> bool:
    """Quản lý chỉnh định mức / duyệt — chỉ khi báo cáo đã nộp."""
    if report.employee_id == viewer.id:
        return False
    if report.is_production_report and report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    from hrm.permissions import can_view_user_report
    return can_view_user_report(viewer, report)


def can_edit_production_report(viewer, report, *, can_submit, is_proxy=False) -> bool:
    if report.employee_id == viewer.id:
        if not production_employee_may_edit(report):
            return False
        return can_submit
    if can_edit_production_norms(viewer, report):
        if report.status != DailyWorkReport.STATUS_SUBMITTED:
            return False
        if report.hod_reviewed:
            return production_manager_may_edit(report)
        return production_employee_may_edit(report)
    if is_proxy:
        if not can_proxy_enter_daily_report(viewer, report.employee):
            return False
        return production_employee_may_edit(report)
    return False


def _production_entry_actor_ok(viewer, report, *, can_submit: bool, is_proxy: bool = False) -> bool:
    if report.employee_id == viewer.id:
        return can_submit
    if is_proxy:
        return can_proxy_enter_daily_report(viewer, report.employee)
    return False


def can_operate_production_entry(viewer, report, *, can_submit: bool, is_proxy: bool = False) -> bool:
    """Nhập tiếp / thêm công đoạn / gửi lại."""
    if not report or not report.pk:
        return False
    if can_edit_production_norms(viewer, report):
        if report.status != DailyWorkReport.STATUS_SUBMITTED:
            return False
        if report.hod_reviewed:
            return production_manager_may_edit(report)
        return production_employee_may_edit(report)
    if not _production_entry_actor_ok(viewer, report, can_submit=can_submit, is_proxy=is_proxy):
        return False
    return production_employee_may_edit(report)


def can_resume_production_entry(viewer, report, *, can_submit: bool, is_proxy: bool = False) -> bool:
    return (
        can_operate_production_entry(viewer, report, can_submit=can_submit, is_proxy=is_proxy)
        and is_production_entry_closed(report)
    )


def can_add_production_entry(viewer, report, *, can_submit: bool, is_proxy: bool = False) -> bool:
    return (
        can_operate_production_entry(viewer, report, can_submit=can_submit, is_proxy=is_proxy)
        and not is_production_entry_closed(report)
    )


def employee_self_submitted_production_report(report) -> bool:
    """NV tự nộp báo cáo (không phải nhập hộ) — quản lý không được sửa giờ."""
    return (
        bool(report and report.pk)
        and report.status == DailyWorkReport.STATUS_SUBMITTED
        and not report.proxy_entered_by_id
    )


def can_proxy_enter_daily_report(viewer, employee) -> bool:
    """Tổ trưởng / cấp trên nhập báo cáo hộ nhân viên (điện thoại hỏng)."""
    from hrm.permissions import can_view_team_reports, get_team_report_members
    if not can_view_team_reports(viewer):
        return False
    return get_team_report_members(viewer).filter(pk=employee.pk).exists()


@transaction.atomic
def ensure_work_day_started(report: DailyWorkReport) -> DailyWorkReport:
    """Tự bắt đầu ngày làm khi vào trang — không tạo phiên công đoạn."""
    if not report.shift_started_at:
        report.report_profile = REPORT_PROFILE_PRODUCTION
        if not report.shift:
            raise ValueError('Báo cáo sản xuất cần chọn ca trước khi bắt đầu.')
        report.shift_started_at = production_server_now()
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


def _product_zero_reason(product: ProductionShiftProduct) -> str:
    """Lý do ghi nhận khi phiên có sản lượng 0."""
    for entry in product.hourly_entries.all():
        reason = (entry.zero_reason or '').strip()
        if reason:
            return reason
    return (product.completion_note or '').strip()


def _product_is_zero_reason_only(product: ProductionShiftProduct) -> bool:
    """Phiên SL=0 chỉ ghi lý do — không đưa vào báo cáo năng suất/hiệu suất."""
    if product.total_quantity is None:
        return False
    try:
        qty = Decimal(str(product.total_quantity))
    except (InvalidOperation, TypeError, ValueError):
        return False
    if qty != 0:
        return False
    return bool(_product_zero_reason(product))


def _products_for_productivity(products: list[ProductionShiftProduct]) -> list[ProductionShiftProduct]:
    return [product for product in products if not _product_is_zero_reason_only(product)]


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
    return normalize_shift(report.shift or DailyWorkReport.SHIFT_MORNING)


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
    """Tạo phiên trống — dùng cho nhập hộ (proxy), không dùng cho NV tự nhập."""
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


def session_in_progress(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    """Phiên đang làm — đã bắt đầu, chưa kết thúc."""
    active = active_product(report)
    if active and active.started_at and not active.ended_at:
        return active
    return None


def session_awaiting_completion(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    """Phiên đã kết thúc — chờ nhập sản lượng và thông tin mã hàng."""
    active = active_product(report)
    if active and active.ended_at and not (active.product_code or '').strip():
        return active
    return None


@transaction.atomic
def start_work_session(report: DailyWorkReport) -> ProductionShiftProduct:
    """Nhân viên bắt đầu công đoạn — mốc thời gian lấy từ VPS tại thời điểm xử lý request."""
    if active_product(report):
        raise ValueError('Đang có công đoạn chưa hoàn tất — kết thúc trước khi bắt đầu mới.')
    now = production_server_now()
    local_now = timezone.localtime(now)
    shift = _shift_for_report(report)
    if not shift_contains_datetime(local_now, report.report_date, shift):
        raise ValueError(
            'Không thể bắt đầu — giờ hệ thống hiện không nằm trong ca báo cáo này.'
        )
    overlaps = slots_overlapping_interval(report.report_date, shift, now, now)
    if overlaps:
        slot_idx = overlaps[0][0]
    else:
        slot_idx = current_slot_index(now, report.report_date, shift)
        if slot_idx is None:
            slot_idx = compute_first_slot_index(report)
    sort_order = report.production_products.count()
    return ProductionShiftProduct.objects.create(
        report=report,
        product_code='',
        process_name='',
        norm_per_hour=None,
        sort_order=sort_order,
        first_slot_index=slot_idx,
        status=ProductionShiftProduct.STATUS_ACTIVE,
        started_at=now,
    )


@transaction.atomic
def end_work_session(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    """Nhân viên kết thúc công đoạn — mốc thời gian lấy từ VPS tại thời điểm xử lý request."""
    active = session_in_progress(report)
    if not active:
        return None
    now = production_server_now()
    if active.started_at and now < active.started_at:
        now = active.started_at
    active.ended_at = now
    active.save(update_fields=['ended_at'])
    return active


def distribute_quantity_to_slots(
    product: ProductionShiftProduct,
    total_quantity,
    *,
    damaged_quantity: int = 0,
    note: str = '',
    zero_reason: str = '',
) -> list[ProductionHourlyQuantity]:
    """Chia đều tổng sản lượng cho từng khung giờ giao với phiên (partial_hours = giờ thực tế)."""
    report = product.report
    shift = _shift_for_product(product)
    start = product.started_at or production_server_now()
    end = product.ended_at or production_server_now()
    overlaps = slots_overlapping_interval(report.report_date, shift, start, end)
    if not overlaps:
        overlaps = [(product.first_slot_index, Decimal('1'))]

    product.first_slot_index = overlaps[0][0]
    product.save(update_fields=['first_slot_index'])

    total_qty = parse_non_negative_decimal(total_quantity, default=Decimal('0'))
    reason = (zero_reason or '').strip()
    if total_qty == 0 and not reason:
        raise ValueError('Cần nhập lý do khi sản lượng bằng 0.')

    product.hourly_entries.all().delete()
    entries: list[ProductionHourlyQuantity] = []
    remaining = total_qty
    damaged_left = max(0, int(damaged_quantity)) if total_qty > 0 else 0
    session_note = (note or '').strip()[:500]
    slot_count = len(overlaps)
    if slot_count <= 0:
        slot_count = 1

    for i, (slot_index, hours) in enumerate(overlaps):
        if i == len(overlaps) - 1:
            qty = remaining
        else:
            share = (total_qty / Decimal(slot_count)).quantize(Decimal('0.01'))
            qty = share
            remaining -= qty

        slot_damaged = 0
        if qty > 0 and damaged_left > 0:
            slot_damaged = damaged_left
            damaged_left = 0

        partial = hours if hours != Decimal('1') else None
        entry = ProductionHourlyQuantity.objects.create(
            product=product,
            slot_index=slot_index,
            quantity=qty,
            damaged_quantity=slot_damaged,
            note=session_note if i == 0 else '',
            partial_hours=partial,
            zero_reason='' if qty > 0 else reason[:200],
        )
        entries.append(entry)
    return entries


@transaction.atomic
def complete_work_session(
    report: DailyWorkReport,
    *,
    product_code: str,
    process_name: str,
    norm_per_hour,
    total_quantity,
    damaged_quantity: int = 0,
    note: str = '',
    zero_reason: str = '',
) -> Optional[ProductionShiftProduct]:
    """Hoàn tất phiên — nhập metadata + tổng sản lượng, chia đều theo khung giờ giao."""
    active = session_awaiting_completion(report)
    if not active:
        active = active_product(report)
        if not active or not active.ended_at:
            return None
    code = (product_code or '').strip()
    process = (process_name or '').strip()
    norm = parse_decimal(norm_per_hour)
    total_qty = parse_non_negative_decimal(total_quantity, default=Decimal('0'))
    reason = (zero_reason or '').strip()

    if total_qty == 0:
        if not reason:
            raise ValueError('Cần nhập lý do khi sản lượng bằng 0.')
        distribute_quantity_to_slots(
            active,
            total_qty,
            zero_reason=reason,
        )
        active.product_code = ''
        active.process_name = ''
        active.norm_per_hour = None
        active.total_quantity = Decimal('0')
        active.total_damaged_quantity = 0
        active.completion_note = reason[:500]
    else:
        if not code or not process or not norm or norm <= 0:
            raise ValueError('Điền đủ mã hàng, tên công đoạn và định mức > 0.')
        distribute_quantity_to_slots(
            active,
            total_qty,
            damaged_quantity=damaged_quantity,
            note=note,
            zero_reason=zero_reason,
        )
        active.product_code = code
        active.process_name = process
        active.norm_per_hour = Decimal(str(norm))
        active.total_quantity = total_qty
        active.total_damaged_quantity = max(0, int(damaged_quantity))
        active.completion_note = (note or '').strip()[:500]

    active.status = ProductionShiftProduct.STATUS_DONE
    active.save()
    return active


@transaction.atomic
def update_session_product(
    product: ProductionShiftProduct,
    *,
    product_code: str,
    process_name: str,
    norm_per_hour,
    total_quantity,
    damaged_quantity: int = 0,
    note: str = '',
    zero_reason: str = '',
) -> ProductionShiftProduct:
    """Chỉnh sửa một công đoạn đã hoàn tất trên màn tổng kết — cập nhật thông tin + chia lại sản lượng."""
    code = (product_code or '').strip()
    process = (process_name or '').strip()
    norm = parse_decimal(norm_per_hour)
    total_qty = parse_non_negative_decimal(total_quantity, default=Decimal('0'))
    reason = (zero_reason or '').strip()

    if total_qty == 0:
        if not reason:
            raise ValueError('Cần nhập lý do khi sản lượng bằng 0.')
        distribute_quantity_to_slots(
            product,
            total_qty,
            zero_reason=reason,
        )
        product.product_code = ''
        product.process_name = ''
        product.norm_per_hour = None
        product.total_quantity = Decimal('0')
        product.total_damaged_quantity = 0
        product.completion_note = reason[:500]
    else:
        if not code or not process or not norm or norm <= 0:
            raise ValueError('Điền đủ mã hàng, tên công đoạn và định mức > 0.')
        distribute_quantity_to_slots(
            product,
            total_qty,
            damaged_quantity=damaged_quantity,
            note=note,
            zero_reason=zero_reason,
        )
        product.product_code = code
        product.process_name = process
        product.norm_per_hour = Decimal(str(norm))
        product.total_quantity = total_qty
        product.total_damaged_quantity = max(0, int(damaged_quantity))
        product.completion_note = (note or '').strip()[:500]

    product.status = ProductionShiftProduct.STATUS_DONE
    product.save()
    return product


@transaction.atomic
def finalize_product_with_metadata(
    report: DailyWorkReport,
    *,
    product_code: str,
    process_name: str,
    norm_per_hour,
) -> Optional[ProductionShiftProduct]:
    """Kết thúc mã hàng — tương thích nhập hộ / dữ liệu cũ đã có sản lượng từng giờ."""
    active = active_product(report)
    if not active:
        return None
    if not active_has_hourly_data(active):
        return None
    active.product_code = product_code.strip()
    active.process_name = process_name.strip()
    active.norm_per_hour = Decimal(str(norm_per_hour))
    active.status = ProductionShiftProduct.STATUS_DONE
    if not active.ended_at:
        active.ended_at = production_server_now()
    active.save()
    ensure_active_work_block(report, after_product=active)
    return active


def unfinalized_active_with_data(report: DailyWorkReport) -> Optional[ProductionShiftProduct]:
    """Phiên chưa hoàn tất — đang làm hoặc chờ nhập thông tin."""
    active = active_product(report)
    if not active:
        return None
    if session_in_progress(report):
        return active
    if session_awaiting_completion(report):
        return active
    if active_has_hourly_data(active):
        return active
    return None


def active_has_hourly_data(product: ProductionShiftProduct) -> bool:
    return product.hourly_entries.filter(quantity__gt=0).exists()


def _entry_hours(entry: ProductionHourlyQuantity) -> Decimal:
    if entry.partial_hours is not None and entry.partial_hours > 0:
        return Decimal(str(entry.partial_hours))
    return Decimal('1')


def save_hourly_entry(
    product: ProductionShiftProduct,
    slot_index: int,
    quantity,
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
    qty = parse_non_negative_decimal(quantity, default=Decimal('0'))
    reason = (zero_reason or '').strip()
    if qty == 0 and not reason:
        raise ValueError('Cần nhập lý do khi sản lượng bằng 0.')
    defaults = {
        'quantity': qty,
        'partial_hours': None,
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


def cumulative_quantity(product: ProductionShiftProduct, up_to_slot: int) -> Decimal:
    total = Decimal('0')
    for entry in product.hourly_entries.filter(
        slot_index__lte=up_to_slot,
        slot_index__gte=product.first_slot_index,
    ).order_by('slot_index'):
        if not _entry_is_filled(entry):
            continue
        metrics = _slot_metrics_from_entry(product, entry)
        if metrics['slot_quantity'] > 0:
            total += metrics['slot_quantity']
    return total


def is_session_reported_product(product: ProductionShiftProduct) -> bool:
    """NV nhập tổng một lần — chia đều sản lượng cho từng khung giờ giao với phiên."""
    return (
        product.total_quantity is not None
        and bool(product.started_at)
        and bool(product.ended_at)
    )


def session_time_label(product: ProductionShiftProduct) -> str:
    started, ended = session_time_displays(product)
    if not started or not ended:
        return ''
    return f'{started} – {ended}'


def session_time_displays(product: ProductionShiftProduct) -> tuple[str, str]:
    """Giờ bắt đầu / kết thúc thực tế (local) cho một công đoạn."""
    if not product.started_at or not product.ended_at:
        return '', ''
    start = timezone.localtime(product.started_at)
    end = timezone.localtime(product.ended_at)
    return start.strftime('%H:%M'), end.strftime('%H:%M')


def product_slot_cell(product: ProductionShiftProduct, slot_index: int) -> dict:
    shift = _shift_for_product(product)
    slot = slot_by_index(slot_index, shift)
    is_overtime = bool(slot and slot.is_overtime)
    if slot_index < product.first_slot_index:
        return {
            'slot_index': slot_index,
            'slot_label': slot.label if slot else str(slot_index),
            'quantity': 0,
            'cumulative': 0,
            'partial_hours': None,
            'display': '',
            'has_data': False,
            'is_na': True,
            'is_overtime': is_overtime,
            'zero_reason': '',
            'damaged_quantity': 0,
            'note': '',
            'entry_id': None,
        }
    entry = product.hourly_entries.filter(slot_index=slot_index).first()
    metrics = _slot_metrics_from_entry(product, entry)
    qty = metrics['slot_quantity']
    reason = (entry.zero_reason or '').strip() if entry else ''
    damaged = entry.damaged_quantity if entry else 0
    entry_note = (entry.note or '').strip() if entry else ''
    filled = _entry_is_filled(entry)
    session_mode = is_session_reported_product(product)
    cum = cumulative_quantity(product, slot_index) if filled and qty > 0 else Decimal('0')
    display = ''
    if entry and filled:
        display = format_production_quantity(qty) if qty > 0 else '0'
    return {
        'slot_index': slot_index,
        'slot_label': slot.label if slot else str(slot_index),
        'quantity': qty,
        'cumulative': cum,
        'display': display,
        'has_data': filled,
        'is_na': False,
        'is_overtime': is_overtime,
        'zero_reason': reason,
        'damaged_quantity': damaged,
        'note': entry_note,
        'entry_id': entry.pk if entry else None,
        'show_cumulative': not session_mode,
        'is_session_split': session_mode,
    }


def _product_has_hourly_data(product: ProductionShiftProduct) -> bool:
    if product.total_quantity is not None:
        return True
    return product.hourly_entries.filter(quantity__gt=0).exists()


def _product_visible_in_grid(product: ProductionShiftProduct) -> bool:
    if _product_has_hourly_data(product):
        return True
    if product.status == ProductionShiftProduct.STATUS_DONE:
        return True
    if product.started_at:
        return True
    return False


def _format_hours_minutes_vn(total_minutes, *, zero_value='0') -> str:
    """< 60 phút → chỉ «X phút»; từ 1 giờ → «X giờ» hoặc «X giờ Y phút»."""
    minutes = int(Decimal(str(total_minutes)).quantize(Decimal('1')))
    if minutes <= 0:
        return zero_value
    if minutes < 60:
        return f'{minutes} phút'
    hours = minutes // 60
    remainder = minutes % 60
    if remainder:
        return f'{hours} giờ {remainder} phút'
    return f'{hours} giờ'


def _format_duration_minutes(total_minutes) -> str:
    return _format_hours_minutes_vn(total_minutes, zero_value='0')


def _timeline_time_display(dt: datetime) -> str:
    return timezone.localtime(dt).strftime('%H:%M')


def _session_event_in_slot(
    product: ProductionShiftProduct,
    slot_start: datetime,
    slot_end: datetime,
) -> bool:
    """Có bắt đầu hoặc kết thúc công đoạn trong khung giờ."""
    if product.started_at and slot_start <= product.started_at < slot_end:
        return True
    if product.ended_at and slot_start <= product.ended_at < slot_end:
        return True
    return False


def _slot_segment_times(report_date, slot) -> dict:
    start = _slot_start_dt(report_date, slot)
    end = _slot_end_dt(report_date, slot)
    minutes = (end - start).total_seconds() / 60
    return {
        'start_display': _timeline_time_display(start),
        'end_display': _timeline_time_display(end),
        'duration_display': _format_duration_minutes(minutes),
        'duration_minutes': minutes,
        'slot_label': slot.label,
        'is_overtime': slot.is_overtime,
    }


def _product_totals(product: ProductionShiftProduct) -> tuple[Decimal, Decimal]:
    """Tổng SL và tổng giờ của mã hàng (chỉ khung có SL > 0, từ khung bắt đầu)."""
    total_qty = Decimal('0')
    total_hours = Decimal('0')
    for entry in product.hourly_entries.all():
        if not _entry_is_filled(entry):
            continue
        if entry.slot_index < product.first_slot_index:
            continue
        if entry.quantity > 0:
            total_qty += Decimal(str(entry.quantity))
            total_hours += _entry_hours(entry)
    return total_qty, total_hours


def _slot_metrics_from_entry(
    product: ProductionShiftProduct,
    entry: ProductionHourlyQuantity | None,
    *,
    product_efficiency_pct: float | None = None,
    product_totals: tuple[Decimal, Decimal] | None = None,
) -> dict:
    """SL khung (báo cáo sản lượng) = tổng SL × thời gian/H ÷ tổng giờ.

    Bằng hiệu suất chung × định mức × thời gian/H nhưng tránh sai số làm tròn nên
    tổng các khung luôn khớp tổng SL mã hàng. Hiệu suất hiển thị lấy chung theo mã
    hàng (báo cáo năng suất). Thiếu định mức thì fallback về SL thực nhập.
    """
    norm = product.norm_per_hour
    hours = _entry_hours(entry) if entry else Decimal('1')
    empty = {
        'efficiency_pct': None,
        'quantity_per_hour': None,
        'slot_quantity': Decimal('0'),
        'hours': float(hours),
    }
    if not entry or not _entry_is_filled(entry):
        return empty

    qty = entry.quantity
    if qty <= 0:
        return empty

    overall_eff = (
        product_efficiency_pct
        if product_efficiency_pct is not None
        else _product_efficiency_pct(product)
    )
    total_qty, total_hours = (
        product_totals if product_totals is not None else _product_totals(product)
    )
    if norm and norm > 0 and total_hours > 0 and hours > 0:
        slot_quantity = (total_qty * hours / total_hours).quantize(Decimal('0.01'))
        quantity_per_hour = float((slot_quantity / hours).quantize(Decimal('0.01')))
        return {
            'efficiency_pct': overall_eff,
            'quantity_per_hour': quantity_per_hour,
            'slot_quantity': slot_quantity,
            'hours': float(hours),
        }

    slot_quantity = Decimal(str(qty)).quantize(Decimal('0.01'))
    quantity_per_hour = float((slot_quantity / hours).quantize(Decimal('0.01'))) if hours > 0 else None
    return {
        'efficiency_pct': None,
        'quantity_per_hour': quantity_per_hour,
        'slot_quantity': slot_quantity,
        'hours': float(hours),
    }


def _product_efficiency_pct(product: ProductionShiftProduct) -> float | None:
    """Hiệu suất chung theo mã hàng — khớp bảng Tổng hợp (Báo cáo năng suất)."""
    norm = product.norm_per_hour
    if not norm or norm <= 0:
        return None
    prod_qty = Decimal('0')
    prod_expected = Decimal('0')
    for entry in product.hourly_entries.order_by('slot_index'):
        if not _entry_is_filled(entry):
            continue
        if entry.slot_index < product.first_slot_index:
            continue
        hours = _entry_hours(entry)
        qty = entry.quantity
        if qty > 0:
            prod_qty += qty
            prod_expected += norm * hours
    if prod_qty > 0 and prod_expected > 0:
        return float((prod_qty / prod_expected * 100).quantize(Decimal('0.01')))
    return None


def _report_efficiency_totals(
    products: list[ProductionShiftProduct],
) -> tuple[Decimal, Decimal, Decimal]:
    """Tổng SL, giờ và SL kỳ vọng (định mức × giờ) — dùng cho hiệu suất TB ngày."""
    total_qty = Decimal('0')
    total_hours = Decimal('0')
    total_expected = Decimal('0')
    for product in products:
        if _product_is_zero_reason_only(product):
            continue
        norm = product.norm_per_hour
        if not norm or norm <= 0:
            continue
        for entry in product.hourly_entries.all():
            if not _entry_is_filled(entry):
                continue
            if entry.slot_index < product.first_slot_index:
                continue
            qty = entry.quantity or Decimal('0')
            if qty <= 0:
                continue
            hours = _entry_hours(entry)
            total_qty += Decimal(str(qty))
            total_hours += hours
            total_expected += norm * hours
    return total_qty, total_hours, total_expected


def _report_overall_efficiency_pct(
    products: list[ProductionShiftProduct],
) -> float | None:
    """Hiệu suất TB trong ngày — trọng số theo giờ từng công đoạn: ΣSL / Σ(định mức × giờ)."""
    total_qty, total_hours, total_expected = _report_efficiency_totals(products)
    if total_expected <= 0 or total_hours <= 0:
        return None
    return float((total_qty / total_expected * 100).quantize(Decimal('0.01')))


def _work_item_from_entry(
    product: ProductionShiftProduct,
    entry: ProductionHourlyQuantity,
    *,
    product_efficiency_pct: float | None = None,
) -> dict:
    code = (product.product_code or '').strip() or '—'
    process = (product.process_name or '').strip() or 'Chưa gắn mã'
    efficiency_pct = (
        product_efficiency_pct
        if product_efficiency_pct is not None
        else _product_efficiency_pct(product)
    )
    metrics = _slot_metrics_from_entry(
        product, entry, product_efficiency_pct=efficiency_pct,
    )
    norm = product.norm_per_hour
    slot_qty = metrics['slot_quantity']
    quantity_per_hour = float(slot_qty) if slot_qty else metrics['quantity_per_hour']
    return {
        'product_code': code,
        'process_name': process,
        'product_id': product.id,
        'quantity': quantity_per_hour,
        'norm_per_hour': float(norm) if norm is not None else None,
        'hours': metrics['hours'],
        'hours_display': _format_hours(metrics['hours']),
        'efficiency_pct': efficiency_pct,
        'damaged_quantity': entry.damaged_quantity or 0,
        'note': (entry.note or '').strip(),
    }


def _work_segment_from_entry(
    product: ProductionShiftProduct,
    entry: ProductionHourlyQuantity,
    slot_times: dict,
) -> dict:
    """Tương thích — gói item theo khung giờ."""
    return {
        'kind': 'work',
        **slot_times,
        'items': [_work_item_from_entry(product, entry)],
    }


def _annotate_product_rowspans(segments: list[dict]) -> None:
    """Mỗi khung giờ hiển thị độc lập — không gộp qua nhiều khung."""
    for segment in segments:
        segment['product_continuation'] = False


def _report_session_bounds(
    products: list[ProductionShiftProduct],
) -> tuple[datetime | None, datetime | None]:
    """Giờ bắt đầu sớm nhất và kết thúc muộn nhất trong ngày."""
    starts = [product.started_at for product in products if product.started_at]
    ends = [product.ended_at for product in products if product.ended_at]
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def _report_has_overtime_activity(
    report: DailyWorkReport,
    products: list[ProductionShiftProduct],
) -> bool:
    """Có ghi nhận sản lượng hoặc phiên công việc trong khung tăng ca."""
    shift = _shift_for_report(report)
    report_date = report.report_date
    ot_slots = [slot for slot in slots_for_shift(shift) if slot.is_overtime]
    if not ot_slots:
        return False
    for product in products:
        for slot in ot_slots:
            slot_start = _slot_start_dt(report_date, slot)
            slot_end = _slot_end_dt(report_date, slot)
            if _session_event_in_slot(product, slot_start, slot_end):
                return True
            for entry in product.hourly_entries.all():
                if entry.slot_index == slot.index and _entry_is_filled(entry):
                    return True
    return False


def _time_efficiency_pct(declared_hours, work_minutes: Decimal):
    """Hiệu suất thời gian = (thời gian thực tế / thời gian làm việc) × 100."""
    if not declared_hours or declared_hours <= 0 or work_minutes <= 0:
        return None
    declared_minutes = Decimal(str(declared_hours)) * Decimal('60')
    pct = work_minutes / declared_minutes * Decimal('100')
    return float(pct.quantize(Decimal('0.01')))


def compute_day_work_waste_summary(
    report: DailyWorkReport,
    products: list[ProductionShiftProduct],
) -> dict:
    """Thời gian làm thực tế và hao phí = giờ khai báo − giờ thực tế."""
    empty = {
        'work_minutes': Decimal('0'),
        'waste_minutes': Decimal('0'),
        'work_minutes_display': '—',
        'waste_minutes_display': '—',
        'has_waste': False,
        'time_efficiency_pct': None,
    }
    actual_start, actual_end = _report_session_bounds(_products_for_productivity(products))
    if not actual_start or not actual_end or actual_end <= actual_start:
        return empty

    actual_start = timezone.localtime(actual_start)
    actual_end = timezone.localtime(actual_end)
    shift = _shift_for_report(report)
    report_date = report.report_date

    work_minutes = Decimal(str((actual_end - actual_start).total_seconds() / 60))
    for break_start, break_end in shift_break_intervals(report_date, shift):
        overlap_start = max(actual_start, break_start)
        overlap_end = min(actual_end, break_end)
        if overlap_end > overlap_start:
            work_minutes -= Decimal(str((overlap_end - overlap_start).total_seconds() / 60))
    if work_minutes < 0:
        work_minutes = Decimal('0')
    work_minutes = work_minutes.quantize(Decimal('1'))

    declared_hours = getattr(report, 'declared_work_hours', None)
    if declared_hours is None or declared_hours <= 0:
        return {
            'work_minutes': work_minutes,
            'waste_minutes': Decimal('0'),
            'work_minutes_display': _format_duration_minutes(work_minutes) if work_minutes > 0 else '—',
            'waste_minutes_display': '—',
            'has_waste': False,
            'time_efficiency_pct': None,
        }

    declared_minutes = (Decimal(str(declared_hours)) * Decimal('60')).quantize(Decimal('1'))
    waste_minutes = declared_minutes - work_minutes
    if waste_minutes < 0:
        waste_minutes = Decimal('0')

    return {
        'work_minutes': work_minutes,
        'waste_minutes': waste_minutes,
        'work_minutes_display': _format_duration_minutes(work_minutes) if work_minutes > 0 else '—',
        'waste_minutes_display': _format_duration_minutes(waste_minutes) if waste_minutes > 0 else '0',
        'has_waste': waste_minutes > 0,
        'time_efficiency_pct': _time_efficiency_pct(declared_hours, work_minutes),
    }


def build_work_day_timeline(report: DailyWorkReport) -> dict:
    """Diễn biến theo khung giờ — chưa ghi nhận chỉ khi cả khung không bắt đầu/kết thúc công đoạn."""
    shift = _shift_for_report(report)
    report_date = report.report_date
    slots = slots_for_shift(shift)

    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by(
            'sort_order', 'id',
        )
    )
    productivity_products = _products_for_productivity(products)
    efficiency_by_product = {
        product.id: _product_efficiency_pct(product)
        for product in productivity_products
    }

    segments: list[dict] = []
    gap_minutes = Decimal('0')

    for index, slot in enumerate(slots):
        slot_start = _slot_start_dt(report_date, slot)
        slot_end = _slot_end_dt(report_date, slot)
        slot_times = _slot_segment_times(report_date, slot)

        entries_in_slot: list[tuple[ProductionShiftProduct, ProductionHourlyQuantity]] = []
        has_session_event = False
        for product in productivity_products:
            if _session_event_in_slot(product, slot_start, slot_end):
                has_session_event = True
            for entry in product.hourly_entries.all():
                if entry.slot_index != slot.index:
                    continue
                if _entry_is_filled(entry):
                    entries_in_slot.append((product, entry))

        if entries_in_slot:
            items = [
                _work_item_from_entry(
                    product,
                    entry,
                    product_efficiency_pct=efficiency_by_product.get(product.id),
                )
                for product, entry in entries_in_slot
            ]
            segments.append({
                'kind': 'work',
                **slot_times,
                'items': items,
            })
        elif has_session_event:
            slot_hours = Decimal(str(slot_times['duration_minutes'])) / Decimal('60')
            segments.append({
                'kind': 'work',
                **slot_times,
                'items': [],
                'label': '—',
                'hours_display': _format_hours(slot_hours),
            })
        else:
            segments.append({
                'kind': 'gap',
                **slot_times,
                'label': 'Chưa ghi nhận công việc',
            })
            gap_minutes += Decimal(str(slot_times['duration_minutes']))

    _annotate_product_rowspans(segments)

    return {
        'segments': segments,
        'has_gaps': any(segment['kind'] == 'gap' for segment in segments),
        'gap_minutes_display': _format_duration_minutes(gap_minutes) if gap_minutes > 0 else '',
    }


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
    productivity_products = _products_for_productivity(products)

    for product in products:
        if _product_is_zero_reason_only(product):
            continue
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
            hours = _entry_hours(entry)
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
            started_display, ended_display = session_time_displays(product)
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
                'started_at_display': started_display,
                'ended_at_display': ended_display,
                'damaged_quantity': product.total_damaged_quantity or 0,
                'note': (product.completion_note or '').strip(),
            })

    hourly_rows.sort(
        key=lambda row: (product_order.get(row['product_id'], 999), row['slot_index'])
    )

    total_qty, total_hours, total_expected = _report_efficiency_totals(productivity_products)
    overall_efficiency_pct = _report_overall_efficiency_pct(productivity_products)
    overall_quantity_per_hour = None
    if total_hours > 0 and total_qty > 0:
        overall_quantity_per_hour = float(
            (total_qty / total_hours).quantize(Decimal('0.01'))
        )

    profile = getattr(report.employee, 'profile', None)
    department_name = profile.department.name if profile and profile.department_id else '—'
    employee_name = (profile.full_name if profile and profile.full_name else report.employee.username)

    proxy_entered_by_name = ''
    if report.proxy_entered_by_id:
        proxy_user = report.proxy_entered_by
        if proxy_user:
            proxy_profile = getattr(proxy_user, 'profile', None)
            proxy_entered_by_name = (
                proxy_profile.full_name
                if proxy_profile and proxy_profile.full_name
                else proxy_user.get_username()
            )

    work_timeline = build_work_day_timeline(report)
    day_times = compute_day_work_waste_summary(report, productivity_products)

    return {
        'hourly_rows': hourly_rows,
        'product_summaries': product_summaries,
        'summary_product_ids': [summary['product_id'] for summary in product_summaries],
        'work_timeline': work_timeline,
        'total_quantity': total_qty,
        'total_hours': float(total_hours),
        'total_hours_display': _format_hours(total_hours),
        'overall_efficiency_pct': overall_efficiency_pct,
        'overall_quantity_per_hour': overall_quantity_per_hour,
        'day_summary': {
            'avg_efficiency_pct': overall_efficiency_pct,
            'time_efficiency_pct': day_times['time_efficiency_pct'],
            'work_time_display': day_times['work_minutes_display'],
            'declared_work_time_display': _format_declared_work_hours(
                getattr(report, 'declared_work_hours', None),
            ),
            'waste_time_display': day_times['waste_minutes_display'],
            'has_waste': day_times['has_waste'],
        },
        'employee_name': employee_name,
        'department_name': department_name,
        'report_date': report.report_date,
        'is_proxy_entered': bool(report.proxy_entered_by_id),
        'proxy_entered_by_name': proxy_entered_by_name,
        'has_data': bool(hourly_rows) or bool(product_summaries),
    }


def update_product_norms(report: DailyWorkReport, norms_by_id: dict) -> int:
    """Quản lý chỉnh định mức theo mã hàng — cập nhật ProductionShiftProduct."""
    return update_production_product_fields(report, norms_by_id=norms_by_id)


def delete_production_products(report: DailyWorkReport, product_ids: list[int]) -> int:
    """Xóa các phiên mã hàng/công đoạn khỏi báo cáo (kèm sản lượng theo giờ)."""
    if not product_ids:
        return 0
    ids = {int(i) for i in product_ids if int(i) > 0}
    if not ids:
        return 0
    qs = report.production_products.filter(id__in=ids)
    count, _detail = qs.delete()
    return count


def update_production_product_fields(
    report: DailyWorkReport,
    *,
    norms_by_id: dict | None = None,
    codes_by_id: dict | None = None,
    processes_by_id: dict | None = None,
) -> int:
    """Quản lý chỉnh mã hàng, công đoạn, định mức trên báo cáo năng suất."""
    norms_by_id = norms_by_id or {}
    codes_by_id = codes_by_id or {}
    processes_by_id = processes_by_id or {}
    if not (norms_by_id or codes_by_id or processes_by_id):
        return 0
    products = {product.id: product for product in report.production_products.all()}
    updated_ids: set[int] = set()
    product_ids = set(norms_by_id) | set(codes_by_id) | set(processes_by_id)
    for product_id in product_ids:
        product = products.get(int(product_id))
        if not product:
            continue
        update_fields: list[str] = []
        if product_id in codes_by_id:
            product.product_code = str(codes_by_id[product_id] or '').strip()[:80]
            update_fields.append('product_code')
        if product_id in processes_by_id:
            product.process_name = str(processes_by_id[product_id] or '').strip()[:120]
            update_fields.append('process_name')
        if product_id in norms_by_id:
            norm = norms_by_id[product_id]
            if norm is None or norm <= 0:
                continue
            product.norm_per_hour = Decimal(str(norm))
            update_fields.append('norm_per_hour')
        if update_fields:
            product.save(update_fields=update_fields)
            updated_ids.add(int(product_id))
    return len(updated_ids)


def format_production_quantity(value) -> str:
    """Hiển thị sản lượng — bỏ phần thập phân .00 khi là số tròn."""
    if value in (None, ''):
        return '0'
    dec = Decimal(str(value))
    if dec == dec.to_integral():
        return str(int(dec))
    text = format(dec.quantize(Decimal('0.01')), 'f')
    return text.rstrip('0').rstrip('.')


def _format_hours(value) -> str:
    dec = Decimal(str(value)).normalize()
    text = format(dec, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return f'{text}h'


def _format_declared_work_hours(hours) -> str:
    """Giờ làm việc nhân viên khai báo khi gửi báo cáo."""
    if hours is None or hours <= 0:
        return '—'
    dec = Decimal(str(hours)).quantize(Decimal('0.01'))
    total_minutes = int((dec * Decimal('60')).quantize(Decimal('1')))
    return _format_hours_minutes_vn(total_minutes, zero_value='—')


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
        if not _product_visible_in_grid(product):
            continue
        zero_only = _product_is_zero_reason_only(product)
        zero_reason = _product_zero_reason(product) if zero_only else ''
        is_unfinalized = (
            product.status == ProductionShiftProduct.STATUS_ACTIVE
            or (
                not (product.product_code or '').strip()
                and not zero_only
            )
        )
        slots = [product_slot_cell(product, i) for i in range(slot_count)]
        session_mode = is_session_reported_product(product)
        cell_total = sum(
            (cell['quantity'] for cell in slots if cell['has_data']),
            Decimal('0'),
        )
        total_qty = product.total_quantity if session_mode and product.total_quantity is not None else cell_total
        started_display, ended_display = session_time_displays(product)
        rows.append({
            'id': product.pk,
            'product_code': product.product_code.strip() if product.product_code else '',
            'process_name': product.process_name.strip() if product.process_name else '',
            'norm_per_hour': float(product.norm_per_hour) if product.norm_per_hour is not None else None,
            'status': product.status,
            'is_unfinalized': is_unfinalized,
            'submitted_locked': product.submitted_locked,
            'first_slot_index': product.first_slot_index,
            'label_code': 'Sản lượng 0' if zero_only else (
                product.product_code.strip() if product.product_code else '—'
            ),
            'label_process': zero_reason if zero_only else (
                product.process_name.strip() if product.process_name else 'Chưa gắn mã'
            ),
            'is_zero_reason_only': zero_only,
            'zero_reason': zero_reason,
            'slots': slots,
            'total_quantity': total_qty,
            'is_session_reported': session_mode,
            'session_total': product.total_quantity,
            'session_damaged': product.total_damaged_quantity or 0,
            'session_note': product.completion_note or '',
            'submitted_locked': product.submitted_locked,
            'session_time_label': session_time_label(product) if session_mode else '',
            'started_at_display': started_display,
            'ended_at_display': ended_display,
        })
    return {
        'slots': [slot_grid_meta(s) for s in hourly_slots],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
        'has_unfinalized': any(r['is_unfinalized'] for r in rows),
        'shift': shift,
        'uses_session_reporting': bool(rows) and all(r['is_session_reported'] for r in rows),
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
    display = ''
    if entry and filled:
        display = format_production_quantity(qty) if qty > 0 else '0'
    slot = slot_by_index(slot_index, shift)
    return {
        'slot_index': slot_index,
        'slot_label': slot.label if slot else str(slot_index),
        'quantity': qty,
        'cumulative': cum if qty else 0,
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
        'slots': [slot_grid_meta(s) for s in hourly_slots],
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


def parse_non_negative_decimal(value, default=Decimal('0')):
    parsed = parse_decimal(value, default=default)
    if parsed is None:
        return default
    return max(Decimal('0'), parsed)


PRODUCTION_WORK_HOURS_MIN = Decimal('8')
PRODUCTION_WORK_HOURS_MAX = Decimal('16')


def validate_production_work_hours(value):
    """Thời gian làm việc khi gửi báo cáo SX: bắt buộc, > 8h và < 16h."""
    hours = parse_decimal(value)
    if hours is None:
        return None, 'Nhập thời gian làm việc.'
    if hours <= PRODUCTION_WORK_HOURS_MIN or hours >= PRODUCTION_WORK_HOURS_MAX:
        return None, 'Thời gian làm việc phải lớn hơn 8 và nhỏ hơn 16 giờ.'
    return hours, ''


def parse_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


# =========================================================
# NHẬP HỘ — bảng Excel theo khung giờ (tổ trưởng nhập cho công nhân)
# =========================================================

def slot_duration_hours(slot) -> Decimal:
    """Độ dài khung giờ (giờ) — dùng làm 'Thời gian/H' khi nhập hộ."""
    from datetime import date as _date, datetime as _dt, timedelta as _td

    base = _date(2000, 1, 1)
    start = _dt.combine(base + _td(days=slot.start_day_offset), slot.start)
    end = _dt.combine(base + _td(days=slot.end_day_offset), slot.end)
    minutes = (end - start).total_seconds() / 60
    return (Decimal(str(minutes)) / Decimal('60')).quantize(Decimal('0.01'))


def _proxy_efficiency(qty, norm, hours) -> Optional[float]:
    if qty and norm and norm > 0 and hours > 0:
        return float((Decimal(str(qty)) / (Decimal(str(norm)) * hours) * 100).quantize(Decimal('0.01')))
    return None


def build_proxy_shift_table(report: DailyWorkReport) -> dict:
    """Bảng nhập hộ 1 ca — mỗi dòng là 1 khung giờ, điền sẵn dữ liệu đã có."""
    shift = _shift_for_report(report)
    slots = slots_for_shift(shift)

    prod_by_slot: dict[int, tuple] = {}
    if report.pk:
        for product in report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id'):
            for entry in product.hourly_entries.all():
                prod_by_slot[entry.slot_index] = (product, entry)

    rows = []
    for slot in slots:
        product, entry = prod_by_slot.get(slot.index, (None, None))
        hours = slot_duration_hours(slot)
        qty = entry.quantity if entry else None
        norm = product.norm_per_hour if product else None
        rows.append({
            'slot_index': slot.index,
            'slot_label': slot.label,
            'hours': hours,
            'hours_display': _format_hours(hours),
            'product_code': (product.product_code or '').strip() if product else '',
            'process_name': (product.process_name or '').strip() if product else '',
            'quantity': format_production_quantity(qty) if qty else '',
            'norm_per_hour': (int(norm) if norm == norm.to_integral() else float(norm)) if norm is not None else '',
            'damaged_quantity': entry.damaged_quantity if entry and entry.damaged_quantity else '',
            'note': (entry.note or '').strip() if entry else '',
            'efficiency_pct': _proxy_efficiency(qty, norm, hours),
        })

    return {
        'shift': shift,
        'rows': rows,
        'has_data': bool(prod_by_slot),
    }


@transaction.atomic
def save_proxy_shift_table(report: DailyWorkReport, rows: list[dict], user) -> dict:
    """
    Lưu bảng nhập hộ 1 ca. `rows` = list theo thứ tự khung giờ, mỗi phần tử:
    {slot_index, product_code, process_name, quantity, norm_per_hour, damaged_quantity, note}.
    Gom các khung giờ liên tiếp cùng (mã hàng + công đoạn + định mức) thành 1 ProductionShiftProduct.
    """
    if not report.pk:
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
    report.report_profile = REPORT_PROFILE_PRODUCTION
    shift = _shift_for_report(report)
    slots = slots_for_shift(shift)
    slot_by_idx = {s.index: s for s in slots}

    report.production_products.all().delete()

    groups: list[dict] = []
    current = None
    for row in sorted(rows, key=lambda r: r.get('slot_index', 0)):
        idx = int(row.get('slot_index', -1))
        if idx not in slot_by_idx:
            continue
        code = (row.get('product_code') or '').strip()
        process = (row.get('process_name') or '').strip()
        qty = parse_non_negative_decimal(row.get('quantity'), default=Decimal('0'))
        norm = parse_decimal(row.get('norm_per_hour'))
        damaged = parse_int(row.get('damaged_quantity'))
        note = (row.get('note') or '').strip()

        has_data = bool(code or process or qty > 0 or note or damaged)
        if not has_data:
            current = None
            continue

        key = (code, process, str(norm) if norm is not None else '')
        cell = {'idx': idx, 'qty': qty, 'damaged': damaged, 'note': note}
        if current and current['key'] == key:
            current['cells'].append(cell)
        else:
            current = {'key': key, 'code': code, 'process': process, 'norm': norm, 'cells': [cell]}
            groups.append(current)

    sort_order = 0
    for g in groups:
        indices = [c['idx'] for c in g['cells']]
        first, last = min(indices), max(indices)
        total = sum((c['qty'] for c in g['cells']), Decimal('0'))
        total_damaged = sum(c['damaged'] for c in g['cells'])
        note_first = next((c['note'] for c in g['cells'] if c['note']), '')
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code=g['code'],
            process_name=g['process'],
            norm_per_hour=g['norm'],
            status=ProductionShiftProduct.STATUS_DONE,
            sort_order=sort_order,
            first_slot_index=first,
            started_at=_slot_start_dt(report.report_date, slot_by_idx[first]),
            ended_at=_slot_end_dt(report.report_date, slot_by_idx[last]),
            total_quantity=total,
            total_damaged_quantity=total_damaged,
            completion_note=note_first[:500],
        )
        sort_order += 1
        for c in g['cells']:
            slot = slot_by_idx[c['idx']]
            hours = slot_duration_hours(slot)
            partial = hours if hours != Decimal('1') else None
            ProductionHourlyQuantity.objects.create(
                product=product,
                slot_index=c['idx'],
                quantity=c['qty'],
                damaged_quantity=c['damaged'],
                note=c['note'][:500],
                partial_hours=partial,
                zero_reason='',
            )

    report.proxy_entered_by = user
    if not report.shift_started_at:
        report.shift_started_at = _slot_start_dt(report.report_date, slots[0])
    if groups:
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submitted_at = timezone.now()
        lock_production_steps_on_submit(report)
    else:
        report.status = DailyWorkReport.STATUS_DRAFT
    report.save()
    return {'groups': len(groups)}


# =========================================================
# NHẬP HỘ — theo công đoạn/mã hàng: chọn nhiều khung giờ + tổng sản lượng
# =========================================================

def _parse_hhmm(value: str) -> time | None:
    value = (value or '').strip()
    if not value:
        return None
    parts = value.split(':')
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def _proxy_clock_datetimes(report_date, shift: str, start_str: str, end_str: str):
    """Chuyển giờ đồng hồ (HH:MM) thành khoảng datetime nằm trong ca."""
    start_t = _parse_hhmm(start_str)
    end_t = _parse_hhmm(end_str)
    if not start_t or not end_t:
        return None

    shift = normalize_shift(shift)
    window_start, window_end = _shift_window(report_date, shift)
    candidates: list[tuple[datetime, datetime]] = []

    for start_off in (0, 1):
        start_day = report_date + timedelta(days=start_off)
        start_dt = timezone.make_aware(datetime.combine(start_day, start_t))
        for end_off in (0, 1, 2):
            end_day = report_date + timedelta(days=end_off)
            end_dt = timezone.make_aware(datetime.combine(end_day, end_t))
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            if start_dt < window_start:
                continue
            if end_dt > window_end:
                end_dt = window_end
            if end_dt <= start_dt or end_dt > window_end:
                continue
            candidates.append((start_dt, end_dt))

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0]


def proxy_slot_windows_for_shift(shift: str) -> list[dict]:
    """Metadata khung giờ ca — dùng tính giao nhau trên trình duyệt."""
    return [
        {
            'index': slot.index,
            'start': f'{slot.start.hour:02d}:{slot.start.minute:02d}',
            'end': f'{slot.end.hour:02d}:{slot.end.minute:02d}',
            'start_day_offset': slot.start_day_offset,
            'end_day_offset': slot.end_day_offset,
        }
        for slot in slots_for_shift(shift)
    ]


def _proxy_session_overlaps(
    report_date,
    shift: str,
    sess: dict,
    slot_by_idx: dict[int, object],
) -> tuple[list[tuple[int, Decimal]], tuple[datetime, datetime] | None]:
    """Trả về các khung giờ giao với khoảng thời gian + interval datetime (nếu có)."""
    start_time = (sess.get('start_time') or '').strip()
    end_time = (sess.get('end_time') or '').strip()
    if start_time and end_time:
        interval = _proxy_clock_datetimes(report_date, shift, start_time, end_time)
        if not interval:
            return [], None
        start_dt, end_dt = interval
        overlaps = slots_overlapping_interval(report_date, shift, start_dt, end_dt)
        return overlaps, (start_dt, end_dt)

    indices = _proxy_session_slot_indices(sess, slot_by_idx)
    if not indices:
        return [], None
    overlaps = [(idx, slot_duration_hours(slot_by_idx[idx])) for idx in indices]
    first, last = indices[0], indices[-1]
    interval = (
        _slot_start_dt(report_date, slot_by_idx[first]),
        _slot_end_dt(report_date, slot_by_idx[last]),
    )
    return overlaps, interval


def _proxy_time_label(t: time) -> str:
    if t.minute:
        return f'{t.hour}h{t.minute:02d}'
    return f'{t.hour}h'


def proxy_boundary_options_for_shift(shift: str) -> tuple[list[dict], list[dict], dict[str, float]]:
    """Mốc bắt đầu/kết thúc theo khung ca — dùng cho nhập hộ."""
    slots = slots_for_shift(shift)
    starts = [{'index': s.index, 'label': _proxy_time_label(s.start)} for s in slots]
    ends = [{'index': s.index, 'label': _proxy_time_label(s.end)} for s in slots]
    hours = {str(s.index): float(slot_duration_hours(s)) for s in slots}
    return starts, ends, hours


def _proxy_session_slot_indices(sess: dict, slot_by_idx: dict[int, object]) -> list[int]:
    """Chuyển start_slot/end_slot (hoặc slots cũ) thành danh sách chỉ số khung giờ."""
    indices: list[int] = []
    for raw in (sess.get('slots') or []):
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if n in slot_by_idx and n not in indices:
            indices.append(n)

    if indices:
        indices.sort()
        return indices

    start_raw = sess.get('start_slot')
    end_raw = sess.get('end_slot')
    if start_raw in (None, '') or end_raw in (None, ''):
        return []
    try:
        start = int(start_raw)
        end = int(end_raw)
    except (TypeError, ValueError):
        return []
    if start not in slot_by_idx or end not in slot_by_idx or end < start:
        return []
    return list(range(start, end + 1))


def _slot_options_for_shift(shift: str) -> list[dict]:
    out = []
    for s in slots_for_shift(shift):
        hours = slot_duration_hours(s)
        out.append({
            'index': s.index,
            'label': s.label,
            'hours': float(hours),
            'hours_display': _format_hours(hours),
        })
    return out


def build_proxy_shift_sessions(report: DailyWorkReport) -> dict:
    """Dữ liệu nhập hộ theo công đoạn — mã hàng + giờ bắt đầu/kết thúc + tổng SL."""
    shift = _shift_for_report(report)
    window_start, window_end = _shift_window(report.report_date, shift)
    sessions = []
    if report.pk:
        for p in report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id'):
            entries = list(p.hourly_entries.all())
            indices = sorted(e.slot_index for e in entries)
            total = p.total_quantity
            if total is None:
                total = sum((e.quantity for e in entries), Decimal('0'))
            norm = p.norm_per_hour
            start_disp, end_disp = session_time_displays(p)
            sessions.append({
                'product_id': p.id,
                'code': (p.product_code or '').strip(),
                'process': (p.process_name or '').strip(),
                'norm': (int(norm) if norm == norm.to_integral() else float(norm)) if norm is not None else '',
                'start_time': start_disp,
                'end_time': end_disp,
                'slots': indices,
                'total': format_production_quantity(total) if total else '',
                'damaged': p.total_damaged_quantity or '',
                'note': (p.completion_note or '').strip(),
            })
    return {
        'shift': shift,
        'slot_windows': proxy_slot_windows_for_shift(shift),
        'slot_windows_json': json.dumps(proxy_slot_windows_for_shift(shift)),
        'shift_window_start': timezone.localtime(window_start).strftime('%H:%M'),
        'shift_window_end': timezone.localtime(window_end).strftime('%H:%M'),
        'sessions': sessions,
        'has_data': bool(sessions),
    }


@transaction.atomic
def save_proxy_shift_sessions(
    report: DailyWorkReport,
    sessions: list[dict],
    user,
    *,
    content_edit_only: bool = False,
) -> dict:
    """
    Lưu nhập hộ theo công đoạn. Mỗi phần tử sessions:
    {product_id?, code, process, norm, start_time, end_time, total, damaged, note} (HH:MM).
    Tổng SL chia theo tỷ lệ thời gian giao với từng khung giờ ca.
  """
    if not report.pk:
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
    report.report_profile = REPORT_PROFILE_PRODUCTION
    shift = _shift_for_report(report)
    slots = slots_for_shift(shift)
    slot_by_idx = {s.index: s for s in slots}

    time_snapshot = {}
    if content_edit_only and report.pk:
        for product in report.production_products.all():
            start_disp, end_disp = session_time_displays(product)
            time_snapshot[product.id] = {
                'start_time': start_disp,
                'end_time': end_disp,
            }

    prior_status = report.status
    prior_submitted_at = report.submitted_at

    report.production_products.all().delete()

    created = 0
    sort_order = 0
    for sess in sessions:
        if content_edit_only:
            product_id = parse_int(sess.get('product_id'), -1)
            if product_id < 0 or product_id not in time_snapshot:
                continue
            sess = {
                **sess,
                'start_time': time_snapshot[product_id]['start_time'],
                'end_time': time_snapshot[product_id]['end_time'],
            }

        code = (sess.get('code') or '').strip()
        process = (sess.get('process') or '').strip()
        norm = parse_decimal(sess.get('norm'))
        total = parse_non_negative_decimal(sess.get('total'), default=Decimal('0'))
        damaged = parse_int(sess.get('damaged'))
        note = (sess.get('note') or '').strip()

        overlaps, interval = _proxy_session_overlaps(
            report.report_date, shift, sess, slot_by_idx,
        )

        has_data = bool(code or process or total > 0 or note or damaged)
        if not has_data or not overlaps or not interval:
            continue

        indices = [idx for idx, _ in overlaps]
        first, last = indices[0], indices[-1]
        start_dt, end_dt = interval
        total_overlap_hours = sum((hours for _, hours in overlaps), Decimal('0'))
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code=code,
            process_name=process,
            norm_per_hour=norm,
            status=ProductionShiftProduct.STATUS_DONE,
            sort_order=sort_order,
            first_slot_index=first,
            started_at=start_dt,
            ended_at=end_dt,
            total_quantity=total,
            total_damaged_quantity=damaged,
            completion_note=note[:500],
        )
        sort_order += 1

        count = len(overlaps)
        remaining = total
        damaged_left = damaged
        for pos, (idx, hours) in enumerate(overlaps):
            if total_overlap_hours > 0:
                if pos == count - 1:
                    qty = remaining
                else:
                    share = (total * hours / total_overlap_hours).quantize(Decimal('0.01'))
                    qty = share
                    remaining -= qty
            elif pos == count - 1:
                qty = remaining
            else:
                share = (total / Decimal(count)).quantize(Decimal('0.01'))
                qty = share
                remaining -= qty
            slot_damaged = 0
            if damaged_left > 0 and qty > 0:
                slot_damaged = damaged_left
                damaged_left = 0
            partial = hours if hours != Decimal('1') else None
            ProductionHourlyQuantity.objects.create(
                product=product,
                slot_index=idx,
                quantity=qty,
                damaged_quantity=slot_damaged,
                note=note[:500] if pos == 0 else '',
                partial_hours=partial,
                zero_reason='',
            )
        created += 1

    if not content_edit_only:
        report.proxy_entered_by = user
    if not report.shift_started_at:
        report.shift_started_at = _slot_start_dt(report.report_date, slots[0])
    if content_edit_only:
        report.status = prior_status
        report.submitted_at = prior_submitted_at
    elif created:
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submitted_at = timezone.now()
        lock_production_steps_on_submit(report)
    else:
        report.status = DailyWorkReport.STATUS_DRAFT
    report.save()

    from reports.models import DailyWorkReportEditLog
    from reports.report_edit_log import log_report_edit

    if content_edit_only:
        log_report_edit(
            report,
            user,
            summary=f'Chỉnh sửa nội dung ({created} công đoạn).',
        )
    elif created:
        log_report_edit(
            report,
            user,
            action=DailyWorkReportEditLog.ACTION_SUBMIT,
            summary=f'Nhập hộ và nộp báo cáo ({created} công đoạn).',
        )
    else:
        log_report_edit(report, user, summary='Lưu nhập hộ (chưa có dữ liệu).')

    return {'sessions': created}
