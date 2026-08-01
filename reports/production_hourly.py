"""Logic báo cáo sản lượng hàng giờ — sản xuất."""

from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import json
from typing import Optional

from django.db import transaction
from django.db.models import Max, Q
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
    if not report or not report.pk:
        return False
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


def ensure_submitted_steps_locked(report: DailyWorkReport) -> int:
    """Chốt công đoạn khi gửi báo cáo (hoặc heal thủ công). Không gọi khi load trang — sẽ ghi đè trạng thái «Cập nhật» sau khi NV sửa."""
    if not report or not report.pk:
        return 0
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return 0
    return lock_production_steps_on_submit(report)


def product_is_submitted_locked(product: ProductionShiftProduct) -> bool:
    return bool(getattr(product, 'submitted_locked', False))


def product_shows_as_submitted(product: ProductionShiftProduct, report: DailyWorkReport) -> bool:
    """Badge «Đã gửi» — chỉ khi công đoạn đã chốt lúc gửi báo cáo."""
    return product_is_submitted_locked(product)


def product_step_display_status(product: ProductionShiftProduct, report: DailyWorkReport) -> str:
    """Trạng thái hiển thị: submitted | updated | pending | draft."""
    if product_is_submitted_locked(product):
        return 'submitted'
    if (
        report
        and report.status == DailyWorkReport.STATUS_SUBMITTED
        and product.status == ProductionShiftProduct.STATUS_DONE
    ):
        return 'updated'
    if product.status == ProductionShiftProduct.STATUS_DONE:
        return 'pending'
    return 'draft'


def employee_can_edit_submitted_report_steps(report: DailyWorkReport) -> bool:
    """NV được sửa công đoạn đã gửi trong 24h khi quản lý chưa duyệt."""
    if not report or not report.pk:
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    return production_employee_may_edit(report)


def manager_may_edit_submitted_production_report(report: DailyWorkReport) -> bool:
    """Quản lý sửa BC đã nộp — đến khi duyệt / không duyệt."""
    if not report or not report.pk:
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    if report.hod_reviewed or getattr(report, 'hod_rejected', False):
        return False
    return True


def viewer_may_edit_declared_work_hours(viewer, report: DailyWorkReport) -> bool:
    """Sửa «Thời gian làm việc»: sau khi gửi được sửa; duyệt/không duyệt thì khóa.

    - Công nhân: còn trong hạn 24h sau nộp (và chưa duyệt).
    - Quản lý: được sửa đến khi duyệt / không duyệt (không bị hạn 24h của NV).
    """
    if not report or not report.pk or not viewer:
        return False
    if report.hod_reviewed or getattr(report, 'hod_rejected', False):
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        # Nhập hộ / nháp: cho phép khai báo giờ khi lưu.
        if report.employee_id == viewer.id:
            return production_employee_may_edit(report)
        return can_proxy_enter_daily_report(viewer, report.employee)
    if report.employee_id == viewer.id:
        return employee_can_edit_submitted_report_steps(report)
    if can_edit_production_norms(viewer, report):
        return manager_may_edit_submitted_production_report(report)
    if can_proxy_enter_daily_report(viewer, report.employee):
        return manager_may_edit_submitted_production_report(report)
    return False


def report_steps_editable_for_viewer(viewer, report: DailyWorkReport) -> bool:
    """Công đoạn đã hoàn tất có được sửa trên màn tổng kết hay không."""
    if not report or not report.pk:
        return False
    if can_edit_production_norms(viewer, report):
        if report.status != DailyWorkReport.STATUS_SUBMITTED:
            return False
        if report.hod_reviewed:
            return production_manager_may_edit(report)
        return manager_may_edit_submitted_production_report(report)
    if report.employee_id != viewer.id:
        return False
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        return employee_can_edit_submitted_report_steps(report)
    return production_employee_may_edit(report)


def viewer_may_edit_stage_time(
    viewer,
    report: DailyWorkReport,
    *,
    product: ProductionShiftProduct | None = None,
    for_wrong_stage: bool = False,
) -> bool:
    """Có được sửa started_at/ended_at công đoạn theo thiết lập chung.

    for_wrong_stage / product sai: nếu bật «Báo cáo sai: cho sửa giờ công đoạn sai»
    thì vẫn cho sửa dù đã tắt quyền sửa giờ thường của CN/QL.
    """
    from reports.report_settings import (
        allow_edit_wrong_stage_time,
        managers_may_edit_stage_time,
        workers_may_edit_stage_time,
    )

    if not viewer or not report:
        return False
    wrong = for_wrong_stage
    if not wrong and product is not None:
        wrong = product_has_manager_fixable_anomaly(product)
    if wrong and allow_edit_wrong_stage_time():
        return True
    if report.employee_id == viewer.id:
        return workers_may_edit_stage_time()
    return managers_may_edit_stage_time()


def product_may_be_edited_by(
    viewer,
    report,
    product: ProductionShiftProduct,
    *,
    content_edit_only: bool = False,
) -> bool:
    if not report or not report.pk or not product:
        return False
    if product.status != ProductionShiftProduct.STATUS_DONE:
        return False
    return report_steps_editable_for_viewer(viewer, report)


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
        return manager_may_edit_submitted_production_report(report)
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
        return manager_may_edit_submitted_production_report(report)
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
    """NV tự nộp báo cáo (không phải nhập hộ) — quản lý sửa qua content_edit_only."""
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


def user_display_name(user) -> str:
    if not user:
        return ''
    profile = getattr(user, 'profile', None)
    if profile and profile.full_name:
        return profile.full_name
    return user.get_username()


def assign_product_updated_by(
    product: ProductionShiftProduct,
    report: DailyWorkReport,
    user,
) -> None:
    """Ghi quản lý vào cột «Cập nhật» khi sửa/thêm công đoạn của NV."""
    if not user or not report or user.id == report.employee_id:
        return
    product.updated_by = user


def product_updated_by_display(product: ProductionShiftProduct, report: DailyWorkReport) -> str:
    if product.updated_by_id:
        return user_display_name(product.updated_by)
    return ''


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
    """Phiên SL=0 chỉ ghi lý do — không tính hiệu suất sản lượng; giờ vẫn ghi nhận thời gian thực tế.

    Nhận cả phiên session (`total_quantity=0`) lẫn nhập theo khung giờ
    (`total_quantity` còn None nhưng có ô SL=0 kèm lý do).
    """
    if _product_has_positive_quantity(product):
        return False
    return bool(_product_zero_reason(product))


def _product_display_work_hours(product: ProductionShiftProduct) -> Decimal:
    """Giờ hiện trên dòng công đoạn — khớp giờ ghi nhận thời gian thực tế."""
    return _product_accounted_work_hours(product)


def _product_accounted_work_hours(product: ProductionShiftProduct) -> Decimal:
    """Giờ ghi vào thời gian thực tế / hiệu suất thời gian — gồm cả công đoạn SL=0."""
    if not _product_has_positive_quantity(product):
        if product.started_at and product.ended_at:
            return session_effective_hours(product)
        hours = Decimal('0')
        for entry in product.hourly_entries.all():
            if not _entry_is_filled(entry):
                continue
            if entry.slot_index < product.first_slot_index:
                continue
            hours += _entry_hours(entry)
        return hours

    norm = product.norm_per_hour
    if not norm or norm <= 0:
        return Decimal('0')

    session_mode = is_session_reported_product(product)
    product_qty = Decimal('0')
    product_hours = Decimal('0')
    for entry in product.hourly_entries.all():
        if not _entry_is_filled(entry):
            continue
        if entry.slot_index < product.first_slot_index:
            continue
        qty = entry.quantity or Decimal('0')
        if qty <= 0:
            continue
        product_qty += Decimal(str(qty))
        product_hours += _entry_hours(entry)
    if product_qty <= 0:
        return Decimal('0')
    if session_mode and product.started_at and product.ended_at:
        return session_effective_hours(product)
    return product_hours


def _products_for_productivity(products: list[ProductionShiftProduct]) -> list[ProductionShiftProduct]:
    """Chỉ công đoạn có SL > 0 — SL=0 không tính vào hiệu suất sản lượng."""
    return [product for product in products if _product_has_positive_quantity(product)]


def _product_should_appear_in_summary(product: ProductionShiftProduct) -> bool:
    """Công đoạn đã ghi nhận — hiện ở chi tiết kể cả khi sản lượng = 0."""
    if _product_is_zero_reason_only(product):
        return True
    if product.status == ProductionShiftProduct.STATUS_DONE:
        return True
    if is_session_reported_product(product) and product.ended_at:
        return True
    return any(
        _entry_is_filled(entry) and entry.slot_index >= product.first_slot_index
        for entry in product.hourly_entries.all()
    )


def list_production_products(report: DailyWorkReport) -> list[ProductionShiftProduct]:
    """Lấy công đoạn; tái dùng prefetch cache nếu có (tránh N+1 trên danh sách)."""
    if not report or not report.pk:
        return []
    cache = getattr(report, '_prefetched_objects_cache', None) or {}
    if 'production_products' in cache:
        products = list(report.production_products.all())
    else:
        products = list(
            report.production_products.prefetch_related('hourly_entries').all()
        )
    products.sort(key=lambda product: (product.sort_order, product.id))
    return products


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
    start_time: str = '',
    end_time: str = '',
    updated_by=None,
    allow_edit_stage_time: bool | None = None,
) -> ProductionShiftProduct:
    """Chỉnh sửa một công đoạn đã hoàn tất trên màn tổng kết — cập nhật thông tin + chia lại sản lượng."""
    code = (product_code or '').strip()
    process = (process_name or '').strip()
    norm = parse_decimal(norm_per_hour)
    total_qty = parse_non_negative_decimal(total_quantity, default=Decimal('0'))
    reason = (zero_reason or '').strip()
    start_hm = (start_time or '').strip()
    end_hm = (end_time or '').strip()

    if start_hm or end_hm:
        if allow_edit_stage_time is False:
            raise ValueError('Không được phép sửa thời gian công đoạn theo thiết lập chung.')
        if allow_edit_stage_time is None and updated_by is not None:
            if not viewer_may_edit_stage_time(updated_by, product.report):
                raise ValueError('Không được phép sửa thời gian công đoạn theo thiết lập chung.')
        if not start_hm or not end_hm:
            raise ValueError('Chọn đủ giờ bắt đầu và giờ kết thúc.')
        report = product.report
        shift = _shift_for_report(report)
        interval = _proxy_clock_datetimes(report.report_date, shift, start_hm, end_hm)
        if not interval:
            raise ValueError('Giờ bắt đầu / kết thúc không hợp lệ hoặc nằm ngoài khung ca.')
        start_dt, end_dt = interval
        for row in report.production_products.filter(
            started_at__isnull=False,
            ended_at__isnull=False,
        ).exclude(pk=product.pk).values('started_at', 'ended_at'):
            old_start = row['started_at']
            old_end = row['ended_at']
            if old_start is None or old_end is None:
                continue
            if start_dt < old_end and end_dt > old_start:
                raise ValueError(
                    'Khoảng giờ bị chồng với công đoạn đã có. '
                    'Có thể bắt đầu đúng bằng giờ kết thúc công đoạn trước.'
                )
        product.started_at = start_dt
        product.ended_at = end_dt

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
    report = product.report
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        product.submitted_locked = False
    if updated_by:
        assign_product_updated_by(product, report, updated_by)
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


def is_empty_active_session(product: Optional[ProductionShiftProduct]) -> bool:
    """Phiên ACTIVE trống — chưa có mã hàng / sản lượng / khung giờ (có thể xóa an toàn)."""
    if not product or product.status != ProductionShiftProduct.STATUS_ACTIVE:
        return False
    if (product.product_code or '').strip() or (product.process_name or '').strip():
        return False
    if product.total_quantity is not None and product.total_quantity > 0:
        return False
    if product.hourly_entries.exists():
        return False
    return True


def discard_empty_active_sessions(report: DailyWorkReport, *, dry_run: bool = False) -> int:
    """Xóa mọi phiên ACTIVE trống trên báo cáo. Trả về số phiên (sẽ) xóa."""
    if not report.pk:
        return 0
    empty = [
        p
        for p in report.production_products.filter(status=ProductionShiftProduct.STATUS_ACTIVE)
        if is_empty_active_session(p)
    ]
    if dry_run or not empty:
        return len(empty)
    ids = [p.pk for p in empty]
    deleted, _ = ProductionShiftProduct.objects.filter(pk__in=ids).delete()
    return deleted


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


def session_effective_hours(product: ProductionShiftProduct) -> Decimal:
    """Giờ làm thực của 1 công đoạn theo mốc bắt đầu/kết thúc, trừ giờ nghỉ ca.

    Dùng mốc tới phút (khớp HH:MM hiển thị) để tránh lệch do giây/micro-giây
    khi nhập tay cộng thời gian.
    """
    if not product.started_at or not product.ended_at:
        return Decimal('0')
    start = timezone.localtime(product.started_at).replace(second=0, microsecond=0)
    end = timezone.localtime(product.ended_at).replace(second=0, microsecond=0)
    if end <= start:
        return Decimal('0')

    minutes = Decimal(str((end - start).total_seconds() / 60))
    report_date = product.report.report_date
    shift = _shift_for_product(product)
    for break_start, break_end in shift_break_intervals(report_date, shift):
        local_break_start = timezone.localtime(break_start).replace(second=0, microsecond=0)
        local_break_end = timezone.localtime(break_end).replace(second=0, microsecond=0)
        overlap_start = max(start, local_break_start)
        overlap_end = min(end, local_break_end)
        if overlap_end > overlap_start:
            minutes -= Decimal(str((overlap_end - overlap_start).total_seconds() / 60))
    if minutes < 0:
        minutes = Decimal('0')
    minutes = minutes.quantize(Decimal('1'))
    return (minutes / Decimal('60')).quantize(Decimal('0.01'))


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
    entry_hours_val = None
    if filled and qty > 0:
        entry_hours_val = float(_entry_hours(entry))
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
        'entry_hours': entry_hours_val,
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
        # Ô SL=0 có lý do: vẫn hiện số 0 / giờ, không tính hiệu suất.
        if _entry_is_filled(entry):
            return {
                'efficiency_pct': None,
                'quantity_per_hour': 0.0,
                'slot_quantity': Decimal('0'),
                'hours': float(hours),
            }
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
    for entry in product.hourly_entries.order_by('slot_index'):
        if not _entry_is_filled(entry):
            continue
        if entry.slot_index < product.first_slot_index:
            continue
        qty = entry.quantity
        if qty > 0:
            prod_qty += qty
    if prod_qty <= 0:
        return None
    if is_session_reported_product(product) and product.started_at and product.ended_at:
        product_hours = session_effective_hours(product)
    else:
        product_hours = Decimal('0')
        for entry in product.hourly_entries.order_by('slot_index'):
            if not _entry_is_filled(entry):
                continue
            if entry.slot_index < product.first_slot_index:
                continue
            qty = entry.quantity
            if qty > 0:
                product_hours += _entry_hours(entry)
    prod_expected = norm * product_hours
    if prod_expected > 0:
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
        session_mode = is_session_reported_product(product)
        product_qty = Decimal('0')
        product_hours = Decimal('0')
        for entry in product.hourly_entries.all():
            if not _entry_is_filled(entry):
                continue
            if entry.slot_index < product.first_slot_index:
                continue
            qty = entry.quantity or Decimal('0')
            if qty <= 0:
                continue
            hours = _entry_hours(entry)
            product_qty += Decimal(str(qty))
            product_hours += hours
        if product_qty <= 0:
            continue
        # Với công đoạn nhập theo phiên, luôn lấy giờ theo mốc bắt đầu/kết thúc (kể cả 0 phút).
        if session_mode and product.started_at and product.ended_at:
            product_hours = session_effective_hours(product)
        total_qty += product_qty
        total_hours += product_hours
        total_expected += norm * product_hours
    return total_qty, total_hours, total_expected


def _product_submit_work_hours(product: ProductionShiftProduct) -> Decimal:
    """Giờ công đoạn khi kiểm tra trước gửi — khớp _report_efficiency_totals."""
    session_mode = is_session_reported_product(product)
    product_hours = Decimal('0')
    has_qty = False
    for entry in product.hourly_entries.all():
        if not _entry_is_filled(entry):
            continue
        if entry.slot_index < product.first_slot_index:
            continue
        qty = entry.quantity or Decimal('0')
        if qty <= 0:
            continue
        has_qty = True
        product_hours += _entry_hours(entry)
    if not has_qty:
        return Decimal('0')
    if session_mode and product.started_at and product.ended_at:
        return session_effective_hours(product)
    return product_hours


def _zero_hour_step_label(product: ProductionShiftProduct) -> str:
    process = (product.process_name or '').strip() or 'công đoạn'
    code = (product.product_code or '').strip()
    if code:
        return f'{process} ({code})'
    return process


def _report_overall_efficiency_pct(
    products: list[ProductionShiftProduct],
) -> float | None:
    """Hiệu suất sản lượng — trọng số theo giờ: ΣSL / Σ(định mức × giờ)."""
    total_qty, total_hours, total_expected = _report_efficiency_totals(products)
    if total_expected <= 0 or total_hours <= 0:
        return None
    return float((total_qty / total_expected * 100).quantize(Decimal('0.01')))


def _combined_efficiency_pct(
    quantity_efficiency_pct: float | None,
    time_efficiency_pct: float | None,
) -> float | None:
    """Hiệu suất TB = hiệu suất sản lượng × hiệu suất thời gian."""
    if quantity_efficiency_pct is None or time_efficiency_pct is None:
        return None
    return float(
        (
            Decimal(str(quantity_efficiency_pct))
            * Decimal(str(time_efficiency_pct))
            / Decimal('100')
        ).quantize(Decimal('0.01'))
    )


def _work_item_from_entry(
    product: ProductionShiftProduct,
    entry: ProductionHourlyQuantity,
    *,
    product_efficiency_pct: float | None = None,
) -> dict:
    zero_only = _product_is_zero_reason_only(product)
    if zero_only:
        code = 'Sản lượng 0'
        process = _product_zero_reason(product) or '—'
        efficiency_pct = None
    else:
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
        'note': (entry.note or '').strip() or (_product_zero_reason(product) if zero_only else ''),
        'is_zero_reason_only': zero_only,
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
    """Thời gian làm thực tế và hao phí = giờ khai báo − giờ thực tế.

    `Thời gian thực tế` = tổng giờ mọi công đoạn đã ghi nhận (kể cả SL=0).
    Công đoạn SL=0 không tính hiệu suất sản lượng nhưng vẫn cộng giờ vào đây.
    """
    empty = {
        'work_minutes': Decimal('0'),
        'waste_minutes': Decimal('0'),
        'work_minutes_display': '—',
        'waste_minutes_display': '—',
        'has_waste': False,
        'time_efficiency_pct': None,
    }
    work_hours = Decimal('0')
    for product in products:
        work_hours += _product_accounted_work_hours(product)

    work_minutes = (work_hours * Decimal('60')).quantize(Decimal('1'))
    if work_minutes <= 0:
        return empty

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
        # Gồm cả SL=0 có lý do — thời gian vẫn ghi nhận, không tính là khoảng trống.
        for product in products:
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
        report.production_products.prefetch_related(
            'hourly_entries',
            'updated_by',
            'updated_by__profile',
        ).order_by('sort_order', 'id')
    )
    product_order = {product.id: index for index, product in enumerate(products)}
    hourly_rows = []
    product_summaries = []
    total_qty = 0
    total_hours = Decimal('0')
    total_expected = Decimal('0')
    productivity_products = _products_for_productivity(products)

    for product in products:
        zero_only = _product_is_zero_reason_only(product)
        if zero_only:
            reason = _product_zero_reason(product)
            prod_hours = _product_display_work_hours(product)
            started_display, ended_display = session_time_displays(product)
            for entry in product.hourly_entries.order_by('slot_index'):
                if not _entry_is_filled(entry):
                    continue
                if entry.slot_index < product.first_slot_index:
                    continue
                slot = slot_by_index(entry.slot_index, shift)
                hours = _entry_hours(entry)
                hourly_rows.append({
                    'product_id': product.id,
                    'slot_index': entry.slot_index,
                    'slot_label': slot.label if slot else str(entry.slot_index),
                    'product_code': 'Sản lượng 0',
                    'process_name': reason or '—',
                    'quantity': entry.quantity or 0,
                    'norm_per_hour': None,
                    'hours': float(hours),
                    'hours_display': _format_hours(hours),
                    'efficiency_pct': None,
                    'zero_reason': reason,
                    'damaged_quantity': entry.damaged_quantity or 0,
                    'note': (entry.note or '').strip() or reason,
                    'is_unfinalized': False,
                    'is_zero_reason_only': True,
                })
            product_summaries.append({
                'product_id': product.id,
                'product_code': 'Sản lượng 0',
                'process_name': reason or '—',
                'quantity': 0,
                'norm_per_hour': None,
                'hours': float(prod_hours),
                'hours_display': _format_hours(prod_hours),
                'efficiency_pct': None,
                'started_at_display': started_display,
                'ended_at_display': ended_display,
                'damaged_quantity': 0,
                'note': reason,
                'updated_by_name': product_updated_by_display(product, report),
                'is_zero_reason_only': True,
            })
            continue

        code = (product.product_code or '').strip() or '—'
        process = (product.process_name or '').strip() or 'Chưa gắn mã'
        norm = product.norm_per_hour
        session_mode = is_session_reported_product(product)
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
                'is_zero_reason_only': False,
            })

        if session_mode and prod_qty > 0 and norm and norm > 0:
            if product.started_at and product.ended_at:
                prod_hours = session_effective_hours(product)
                prod_expected = norm * prod_hours

        started_display, ended_display = session_time_displays(product)
        if prod_qty > 0 and norm and norm > 0:
            product_summaries.append({
                'product_id': product.id,
                'product_code': code,
                'process_name': process,
                'quantity': prod_qty,
                'norm_per_hour': float(norm),
                'hours': float(prod_hours),
                'hours_display': _format_hours(prod_hours),
                'efficiency_pct': (
                    float(
                        (Decimal(prod_qty) / prod_expected * 100).quantize(Decimal('0.01'))
                    )
                    if prod_expected > 0 else None
                ),
                'started_at_display': started_display,
                'ended_at_display': ended_display,
                'damaged_quantity': product.total_damaged_quantity or 0,
                'note': (product.completion_note or '').strip(),
                'updated_by_name': product_updated_by_display(product, report),
                'is_zero_reason_only': False,
            })
        elif _product_should_appear_in_summary(product) and not _product_has_positive_quantity(product):
            # Công đoạn SL=0: hiện ở chi tiết báo cáo, không tính hiệu suất.
            display_hours = _product_display_work_hours(product)
            reason = _product_zero_reason(product)
            product_summaries.append({
                'product_id': product.id,
                'product_code': code,
                'process_name': process,
                'quantity': 0,
                'norm_per_hour': float(norm) if norm and norm > 0 else None,
                'hours': float(display_hours),
                'hours_display': _format_hours(display_hours),
                'efficiency_pct': None,
                'started_at_display': started_display,
                'ended_at_display': ended_display,
                'damaged_quantity': product.total_damaged_quantity or 0,
                'note': (product.completion_note or '').strip() or reason,
                'updated_by_name': product_updated_by_display(product, report),
                'is_zero_reason_only': True,
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
        proxy_entered_by_name = user_display_name(report.proxy_entered_by)

    work_timeline = build_work_day_timeline(report)
    day_times = compute_day_work_waste_summary(report, products)
    quantity_efficiency_pct = overall_efficiency_pct
    time_efficiency_pct = day_times['time_efficiency_pct']
    avg_efficiency_pct = _combined_efficiency_pct(
        quantity_efficiency_pct,
        time_efficiency_pct,
    )
    total_damaged = sum(int(product.total_damaged_quantity or 0) for product in products)

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
            'avg_efficiency_pct': avg_efficiency_pct,
            'quantity_efficiency_pct': quantity_efficiency_pct,
            'time_efficiency_pct': time_efficiency_pct,
            'total_damaged': total_damaged,
            'total_damaged_display': format_production_quantity(total_damaged),
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
    updated_by=None,
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
            if updated_by:
                assign_product_updated_by(product, report, updated_by)
                update_fields.append('updated_by')
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
    dec = Decimal(str(value)).quantize(Decimal('0.01'))
    total_minutes = int((dec * Decimal('60')).quantize(Decimal('1')))
    return _format_hours_minutes_vn(total_minutes, zero_value='0 phút')


def _format_declared_work_hours(hours) -> str:
    """Giờ làm việc nhân viên khai báo khi gửi báo cáo."""
    if hours is None or hours <= 0:
        return '—'
    dec = Decimal(str(hours)).quantize(Decimal('0.01'))
    total_minutes = int((dec * Decimal('60')).quantize(Decimal('1')))
    return _format_hours_minutes_vn(total_minutes, zero_value='—')


def build_hourly_grid(report: DailyWorkReport, *, steps_editable: bool | None = None) -> dict:
    """Bảng tổng — gồm mã đã kết thúc và phiên đang nhập (chưa gắn mã hàng)."""
    shift = _shift_for_report(report)
    slot_count = slot_count_for_shift(shift)
    hourly_slots = slots_for_shift(shift)
    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    if steps_editable is None:
        steps_editable = (
            report.status != DailyWorkReport.STATUS_SUBMITTED
            or employee_can_edit_submitted_report_steps(report)
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
        marked_submitted = product_is_submitted_locked(product)
        step_status = product_step_display_status(product, report)
        can_edit_step = (
            product.status == ProductionShiftProduct.STATUS_DONE
            and steps_editable
        )
        session_hours = None
        if session_mode and product.started_at and product.ended_at:
            session_hours = float(session_effective_hours(product))
        rows.append({
            'id': product.pk,
            'product_code': product.product_code.strip() if product.product_code else '',
            'process_name': product.process_name.strip() if product.process_name else '',
            'norm_per_hour': float(product.norm_per_hour) if product.norm_per_hour is not None else None,
            'status': product.status,
            'is_unfinalized': is_unfinalized,
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
            'session_effective_hours': session_hours,
            'step_display_status': step_status,
            'can_edit_step': can_edit_step,
            'submitted_locked': marked_submitted,
            'session_total': product.total_quantity,
            'session_damaged': product.total_damaged_quantity or 0,
            'session_note': product.completion_note or '',
            'session_time_label': session_time_label(product) if session_mode else '',
            'started_at_display': started_display,
            'ended_at_display': ended_display,
        })
    productive = _products_for_productivity(products)
    return {
        'slots': [
            {**slot_grid_meta(s), 'duration_hours': float(slot_duration_hours(s))}
            for s in hourly_slots
        ],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
        'has_unfinalized': any(r['is_unfinalized'] for r in rows),
        'shift': shift,
        'uses_session_reporting': bool(rows) and all(r['is_session_reported'] for r in rows),
        'overall_efficiency_pct': _report_overall_efficiency_pct(productive),
        'max_submit_efficiency_pct': PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT,
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
    hours = slot_duration_hours(slot) if slot else Decimal('1')
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
        'entry_hours': float(hours),
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
    productive = _products_for_productivity(products)
    return {
        'slots': [
            {**slot_grid_meta(s), 'duration_hours': float(slot_duration_hours(s))}
            for s in hourly_slots
        ],
        'rows': rows,
        'grand_total': sum(r['total_quantity'] for r in rows),
        'has_unfinalized': any(r['is_unfinalized'] for r in rows),
        'proxy_mode': True,
        'shift': shift,
        'overall_efficiency_pct': _report_overall_efficiency_pct(productive),
        'max_submit_efficiency_pct': PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT,
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
    """Nhận cả dấu chấm và dấu phẩy thập phân (9.5 / 9,5)."""
    if value in (None, ''):
        return default
    try:
        text = (
            str(value)
            .strip()
            .replace('\u00a0', '')
            .replace(' ', '')
            .replace(',', '.')
        )
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def parse_non_negative_decimal(value, default=Decimal('0')):
    parsed = parse_decimal(value, default=default)
    if parsed is None:
        return default
    return max(Decimal('0'), parsed)


PRODUCTION_WORK_HOURS_MIN = Decimal('7.50')
PRODUCTION_WORK_HOURS_MAX = Decimal('16')
PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT = 200


def _production_work_hours_bounds():
    from reports.report_settings import report_work_hours_max, report_work_hours_min

    try:
        low = report_work_hours_min()
        high = report_work_hours_max()
    except Exception:
        low = PRODUCTION_WORK_HOURS_MIN
        high = PRODUCTION_WORK_HOURS_MAX
    if low >= high:
        return PRODUCTION_WORK_HOURS_MIN, PRODUCTION_WORK_HOURS_MAX
    return low, high


def validate_production_work_hours(value):
    """Thời gian làm việc khi gửi báo cáo SX: bắt buộc, trong khoảng thiết lập chung."""
    hours = parse_decimal(value)
    if hours is None:
        return None, 'Nhập thời gian làm việc.'
    low, high = _production_work_hours_bounds()
    if hours < low or hours >= high:
        low_s = f'{low:.2f}'.replace('.', ',')
        high_s = f'{(high - Decimal("0.01")):.2f}'.replace('.', ',')
        return None, f'Thời gian làm việc phải từ {low_s} đến {high_s} giờ.'
    return hours, ''


def resolve_declared_work_hours_for_save(
    report: DailyWorkReport,
    raw_value,
    *,
    allow_keep_existing: bool = True,
):
    """Giữ thời gian làm việc đã có nếu form không gửi lại giá trị mới."""
    raw = (raw_value or '').strip() if raw_value is not None else ''
    if allow_keep_existing and not raw and report.declared_work_hours is not None:
        return report.declared_work_hours, ''
    return validate_production_work_hours(raw or None)


def _product_has_positive_quantity(product: ProductionShiftProduct) -> bool:
    for entry in product.hourly_entries.all():
        if not _entry_is_filled(entry):
            continue
        if entry.slot_index < product.first_slot_index:
            continue
        if (entry.quantity or Decimal('0')) > 0:
            return True
    return (product.total_quantity or Decimal('0')) > 0


def product_has_zero_duration_anomaly(product: ProductionShiftProduct) -> bool:
    """Công đoạn có SL nhưng thời gian bắt đầu = kết thúc (0 phút)."""
    if _product_is_zero_reason_only(product):
        return False
    if not _product_has_positive_quantity(product):
        return False
    if product.started_at and product.ended_at:
        start = timezone.localtime(product.started_at).replace(second=0, microsecond=0)
        end = timezone.localtime(product.ended_at).replace(second=0, microsecond=0)
        if start == end:
            return True
    return _product_submit_work_hours(product) <= 0


def product_has_efficiency_anomaly(product: ProductionShiftProduct) -> bool:
    """Hiệu suất công đoạn > 200% hoặc <= 0%."""
    efficiency = _product_efficiency_pct(product)
    if efficiency is None:
        return False
    return efficiency <= 0 or efficiency > PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT


def product_has_manager_fixable_anomaly(product: ProductionShiftProduct) -> bool:
    """Công đoạn sai — quản lý được phép sửa khi báo cáo chưa nộp."""
    if _product_is_zero_reason_only(product):
        return False
    return (
        product_has_zero_duration_anomaly(product)
        or product_has_efficiency_anomaly(product)
    )


def anomaly_product_ids_for_report(report: DailyWorkReport) -> set[int]:
    if not report or not report.pk:
        return set()
    products = list_production_products(report)
    return {
        product.id
        for product in _products_for_productivity(products)
        if product_has_manager_fixable_anomaly(product)
    }


def report_has_manager_fixable_anomaly(report: DailyWorkReport) -> bool:
    """Báo cáo chưa nộp có công đoạn sai — quản lý được phép chỉnh sửa."""
    if not report or not report.pk:
        return False
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        return False
    return bool(anomaly_product_ids_for_report(report))


def can_manager_edit_unsubmitted_production_report(viewer, report: DailyWorkReport) -> bool:
    if not report or not report.pk or report.status == DailyWorkReport.STATUS_SUBMITTED:
        return False
    if not can_proxy_enter_daily_report(viewer, report.employee):
        return False
    return report_has_manager_fixable_anomaly(report)


def validate_production_submit_efficiency(report: DailyWorkReport) -> tuple[float | None, str]:
    """Chặn gửi nếu hiệu suất > 200% hoặc công đoạn có SL nhưng thời gian 0 phút."""
    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    productive = _products_for_productivity(products)
    for product in productive:
        if product_has_zero_duration_anomaly(product):
            return None, (
                f'Số liệu bạn gửi sai — {_zero_hour_step_label(product)} có sản lượng '
                'nhưng thời gian công đoạn 0 phút. Vui lòng kiểm tra lại.'
            )
        if product_has_efficiency_anomaly(product):
            efficiency = _product_efficiency_pct(product)
            if efficiency is not None and efficiency <= 0:
                return efficiency, (
                    'Số liệu bạn gửi sai — có công đoạn hiệu suất không hợp lệ. '
                    'Vui lòng kiểm tra lại sản lượng, định mức và thời gian công đoạn.'
                )
            if efficiency is not None:
                pct_text = format(efficiency, '.2f').rstrip('0').rstrip('.')
                return efficiency, (
                    f'Số liệu bạn gửi sai — công đoạn {_zero_hour_step_label(product)} '
                    f'hiệu suất {pct_text}% vượt {PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT}%. '
                    'Vui lòng kiểm tra lại sản lượng và định mức.'
                )

    efficiency = _report_overall_efficiency_pct(products)
    if efficiency is not None and efficiency < 0:
        return efficiency, (
            'Số liệu bạn gửi sai — hiệu suất sơ bộ không hợp lệ. '
            'Vui lòng kiểm tra lại sản lượng, định mức và thời gian công đoạn.'
        )
    if efficiency is not None and efficiency > PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT:
        pct_text = format(efficiency, '.2f').rstrip('0').rstrip('.')
        return efficiency, (
            f'Số liệu bạn gửi sai — hiệu suất sơ bộ {pct_text}% vượt '
            f'{PRODUCTION_MAX_SUBMIT_EFFICIENCY_PCT}%. Vui lòng kiểm tra lại sản lượng và định mức.'
        )
    return efficiency, ''


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
        from reports.report_submit_time import resolve_submitted_at

        now = timezone.now()
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submit_clicked_at = now
        report.submitted_at = resolve_submitted_at(report, now)
        report.auto_submitted = False
        lock_production_steps_on_submit(report)
    else:
        report.status = DailyWorkReport.STATUS_DRAFT
        report.auto_submitted = False
    report.save()

    if groups:
        from reports.report_lock import auto_approve_fully_proxy_entered_report

        auto_approve_fully_proxy_entered_report(report)

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
    """Chuyển giờ đồng hồ (HH:MM) thành khoảng datetime nằm trong ca.

    Ca tối qua nửa đêm: giờ sáng (0h–5h) phải gắn ngày hôm sau (start_day_offset=1),
    không lấy sáng cùng ngày báo cáo.
    """
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
        if start_dt < window_start or start_dt >= window_end:
            continue
        for end_off in (0, 1, 2):
            end_day = report_date + timedelta(days=end_off)
            end_dt = timezone.make_aware(datetime.combine(end_day, end_t))
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            # Không clamp về hết ca — tránh kéo dài sai (vd 22h–2h → 22h–5h).
            if end_dt > window_end or end_dt <= start_dt:
                continue
            if not slots_overlapping_interval(report_date, shift, start_dt, end_dt):
                continue
            candidates.append((start_dt, end_dt))

    if not candidates:
        return None
    # Trong các khoảng hợp lệ: chọn mốc bắt đầu sớm nhất (trong khung ca).
    candidates.sort(key=lambda pair: (pair[0], pair[1]))
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


def _proxy_session_dict_from_product(product: ProductionShiftProduct) -> dict:
    entries = list(product.hourly_entries.all())
    indices = sorted(e.slot_index for e in entries)
    total = product.total_quantity
    if total is None:
        total = sum((e.quantity for e in entries), Decimal('0'))
    norm = product.norm_per_hour
    start_disp, end_disp = session_time_displays(product)
    return {
        'product_id': product.id,
        'code': (product.product_code or '').strip(),
        'process': (product.process_name or '').strip(),
        'norm': (int(norm) if norm == norm.to_integral() else float(norm)) if norm is not None else '',
        'start_time': start_disp,
        'end_time': end_disp,
        'slots': indices,
        'total': format_production_quantity(total) if total else '',
        'damaged': product.total_damaged_quantity or '',
        'note': (product.completion_note or '').strip(),
    }


def build_proxy_shift_sessions(report: DailyWorkReport) -> dict:
    """Dữ liệu nhập hộ theo công đoạn — mã hàng + giờ bắt đầu/kết thúc + tổng SL."""
    shift = _shift_for_report(report)
    window_start, window_end = _shift_window(report.report_date, shift)
    sessions = []
    if report.pk:
        for product in report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id'):
            sessions.append(_proxy_session_dict_from_product(product))
    return {
        'shift': shift,
        'slot_windows': proxy_slot_windows_for_shift(shift),
        'slot_windows_json': json.dumps(proxy_slot_windows_for_shift(shift)),
        'shift_window_start': timezone.localtime(window_start).strftime('%H:%M'),
        'shift_window_end': timezone.localtime(window_end).strftime('%H:%M'),
        'sessions': sessions,
        'has_data': bool(sessions),
    }


def enrich_proxy_shift_sessions_for_anomaly_fix(data: dict, report: DailyWorkReport) -> dict:
    """Đánh dấu công đoạn đúng (khóa) / sai (cho sửa) trên form sửa báo cáo chưa nộp."""
    from reports.report_settings import allow_edit_wrong_stage_time

    if not report or not report.pk or report.status == DailyWorkReport.STATUS_SUBMITTED:
        return data
    anomaly_ids = anomaly_product_ids_for_report(report)
    if not anomaly_ids:
        return data
    may_edit_wrong_times = allow_edit_wrong_stage_time()
    sessions = []
    for sess in data.get('sessions') or []:
        product_id = sess.get('product_id')
        is_anomaly = product_id in anomaly_ids
        sessions.append({
            **sess,
            'is_anomaly': is_anomaly,
            'session_locked': not is_anomaly,
            'lock_stage_times': bool(is_anomaly and not may_edit_wrong_times),
        })
    return {**data, 'sessions': sessions, 'anomaly_fix_mode': True}


def _build_proxy_time_snapshot(report: DailyWorkReport) -> dict[int, dict]:
    snapshot: dict[int, dict] = {}
    for product in report.production_products.all():
        start_disp, end_disp = session_time_displays(product)
        snapshot[product.id] = {
            'start_time': start_disp,
            'end_time': end_disp,
            'started_at': product.started_at,
            'ended_at': product.ended_at,
        }
    return snapshot


def _proxy_session_has_input(sess: dict) -> bool:
    code = (sess.get('code') or '').strip()
    process = (sess.get('process') or '').strip()
    total = parse_non_negative_decimal(sess.get('total'), default=Decimal('0'))
    damaged = parse_int(sess.get('damaged'))
    note = (sess.get('note') or '').strip()
    start_time = (sess.get('start_time') or '').strip()
    end_time = (sess.get('end_time') or '').strip()
    return bool(code or process or total > 0 or note or damaged or start_time or end_time)


def _resolve_proxy_session_interval(
    report_date,
    shift: str,
    sess: dict,
    slot_by_idx: dict[int, object],
    *,
    snapshot: dict[int, dict],
    content_edit_only: bool,
) -> tuple[list[tuple[int, Decimal]], tuple[datetime, datetime] | None]:
    """Xác định khung giờ giao — ưu tiên giờ form; thiếu thì lấy mốc gốc đã nộp."""
    start_time = (sess.get('start_time') or '').strip()
    end_time = (sess.get('end_time') or '').strip()
    if start_time and end_time:
        return _proxy_session_overlaps(report_date, shift, sess, slot_by_idx)

    product_id = parse_int(sess.get('product_id'), -1)
    if content_edit_only and product_id >= 0 and product_id in snapshot:
        snap = snapshot[product_id]
        start_dt = snap.get('started_at')
        end_dt = snap.get('ended_at')
        if start_dt and end_dt:
            overlaps = slots_overlapping_interval(report_date, shift, start_dt, end_dt)
            if overlaps:
                return overlaps, (start_dt, end_dt)
    return _proxy_session_overlaps(report_date, shift, sess, slot_by_idx)


def _normalize_anomaly_fix_sessions(report: DailyWorkReport, sessions: list[dict]) -> list[dict]:
    """Chỉ cho sửa công đoạn sai — công đoạn đúng giữ nguyên từ DB."""
    from reports.report_settings import allow_edit_wrong_stage_time

    products = list(
        report.production_products.prefetch_related('hourly_entries').order_by('sort_order', 'id')
    )
    if not products:
        raise ValueError('Báo cáo không có công đoạn để lưu.')
    anomaly_ids = anomaly_product_ids_for_report(report)
    if not anomaly_ids:
        raise ValueError('Báo cáo không còn công đoạn cần sửa.')

    locked_forms = {
        product.id: _proxy_session_dict_from_product(product)
        for product in products
    }
    submitted_by_id: dict[int, dict] = {}
    for raw_sess in sessions:
        product_id = parse_int(raw_sess.get('product_id'), -1)
        if product_id < 0:
            raise ValueError(
                'Không được thêm công đoạn mới — chỉ sửa các công đoạn sai hiệu suất hoặc thời gian.'
            )
        if product_id not in locked_forms:
            raise ValueError('Công đoạn không hợp lệ.')
        submitted_by_id[product_id] = dict(raw_sess)

    if set(submitted_by_id) != set(locked_forms):
        raise ValueError(
            'Phải giữ nguyên các công đoạn đúng — không được xóa công đoạn đã khóa.'
        )

    may_edit_wrong_times = allow_edit_wrong_stage_time()
    normalized: list[dict] = []
    for product in products:
        if product.id in anomaly_ids:
            sess = submitted_by_id[product.id]
            if not may_edit_wrong_times:
                locked = locked_forms[product.id]
                sess = {
                    **sess,
                    'start_time': locked.get('start_time') or '',
                    'end_time': locked.get('end_time') or '',
                }
            normalized.append(sess)
        else:
            normalized.append(locked_forms[product.id])
    return normalized


def _prepare_proxy_sessions_for_save(
    report: DailyWorkReport,
    sessions: list[dict],
    *,
    content_edit_only: bool,
    preserve_draft: bool = False,
    snapshot: dict[int, dict],
) -> list[dict]:
    shift = _shift_for_report(report)
    slot_by_idx = {s.index: s for s in slots_for_shift(shift)}
    prepared: list[dict] = []

    for raw_sess in sessions:
        sess = dict(raw_sess)
        if content_edit_only:
            product_id = parse_int(sess.get('product_id'), -1)
            if product_id >= 0 and product_id in snapshot:
                from reports.report_settings import (
                    allow_edit_wrong_stage_time,
                    managers_may_edit_stage_time,
                )
                may_change_times = (
                    managers_may_edit_stage_time() or allow_edit_wrong_stage_time()
                )
                # Giữ giờ gốc khi form không gửi, hoặc khi thiết lập không cho sửa giờ.
                if not may_change_times or not (sess.get('start_time') or '').strip():
                    sess['start_time'] = snapshot[product_id]['start_time']
                if not may_change_times or not (sess.get('end_time') or '').strip():
                    sess['end_time'] = snapshot[product_id]['end_time']

        if not _proxy_session_has_input(sess):
            continue

        code = (sess.get('code') or '').strip()
        process = (sess.get('process') or '').strip()
        norm = parse_decimal(sess.get('norm'))
        total = parse_non_negative_decimal(sess.get('total'), default=Decimal('0'))
        damaged = parse_int(sess.get('damaged'))
        note = (sess.get('note') or '').strip()

        overlaps, interval = _resolve_proxy_session_interval(
            report.report_date,
            shift,
            sess,
            slot_by_idx,
            snapshot=snapshot,
            content_edit_only=content_edit_only,
        )
        if not overlaps or not interval:
            continue

        prepared.append({
            'code': code,
            'process': process,
            'norm': norm,
            'total': total,
            'damaged': damaged,
            'note': note,
            'overlaps': overlaps,
            'interval': interval,
            'product_id': (
                parse_int(sess.get('product_id'), -1)
                if content_edit_only or preserve_draft
                else -1
            ),
        })

    if any(_proxy_session_has_input(sess) for sess in sessions) and not prepared:
        raise ValueError(
            'Không lưu được công đoạn nào. Kiểm tra mã hàng, sản lượng và khung giờ bắt đầu/kết thúc.'
        )
    return prepared


def _snapshot_from_prepared_proxy_item(item: dict) -> dict[str, str]:
    start_dt, end_dt = item['interval']
    start_disp = timezone.localtime(start_dt).strftime('%H:%M')
    end_disp = timezone.localtime(end_dt).strftime('%H:%M')
    norm = item.get('norm')
    return {
        'code': (item.get('code') or '').strip() or '—',
        'process': (item.get('process') or '').strip() or '—',
        'norm': format_production_quantity(norm) if norm and norm > 0 else '—',
        'quantity': format_production_quantity(item.get('total') or 0),
        'damaged': str(max(0, int(item.get('damaged') or 0))),
        'time': f'{start_disp}–{end_disp}' if start_disp and end_disp else '—',
        'note': (item.get('note') or '').strip() or '—',
    }


def _build_proxy_product_meta(report: DailyWorkReport) -> dict[int, dict]:
    from reports.production_edit_log import snapshot_production_session

    meta: dict[int, dict] = {}
    for product in report.production_products.all():
        meta[product.id] = {
            'updated_by_id': product.updated_by_id,
            'snapshot': snapshot_production_session(product),
        }
    return meta


def _resolve_proxy_product_updated_by_id(
    *,
    track_manager_updates: bool,
    user,
    report: DailyWorkReport,
    product_id: int,
    old_meta: dict[int, dict],
    new_snap: dict[str, str],
) -> int | None:
    """Chỉ gán «Cập nhật» cho công đoạn mới hoặc có thay đổi nội dung."""
    if not track_manager_updates:
        return None
    if not user or user.id == report.employee_id:
        return None
    if product_id >= 0 and product_id in old_meta:
        old = old_meta[product_id]
        if old['snapshot'] == new_snap:
            return old.get('updated_by_id')
        return user.id
    return user.id


@transaction.atomic
def save_proxy_shift_sessions(
    report: DailyWorkReport,
    sessions: list[dict],
    user,
    *,
    content_edit_only: bool = False,
    preserve_draft: bool = False,
) -> dict:
    """
    Lưu nhập hộ theo công đoạn. Mỗi phần tử sessions:
    {product_id?, code, process, norm, start_time, end_time, total, damaged, note} (HH:MM).
    Tổng SL chia theo tỷ lệ thời gian giao với từng khung giờ ca.

    preserve_draft: quản lý sửa báo cáo chưa nộp (sai số liệu) — giữ trạng thái draft,
    ghi cột «Cập nhật» và lịch sử, không tự nộp báo cáo.
    """
    if not report.pk:
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
    report.report_profile = REPORT_PROFILE_PRODUCTION
    shift = _shift_for_report(report)
    slots = slots_for_shift(shift)

    track_manager_updates = content_edit_only or preserve_draft
    snapshot = _build_proxy_time_snapshot(report) if content_edit_only and report.pk else {}

    prior_status = report.status
    prior_submitted_at = report.submitted_at
    prior_submit_clicked_at = report.submit_clicked_at

    if preserve_draft:
        sessions = _normalize_anomaly_fix_sessions(report, sessions)

    prepared = _prepare_proxy_sessions_for_save(
        report,
        sessions,
        content_edit_only=content_edit_only,
        preserve_draft=preserve_draft,
        snapshot=snapshot,
    )

    from reports.production_edit_log import (
        collect_new_sessions_detail,
        collect_proxy_save_change_detail,
    )

    if track_manager_updates:
        change_detail = collect_proxy_save_change_detail(
            report,
            sessions,
            content_edit_only=content_edit_only,
        )
    else:
        change_detail = ''

    old_meta = _build_proxy_product_meta(report) if track_manager_updates and report.pk else {}

    report.production_products.all().delete()

    created = 0
    sort_order = 0
    for item in prepared:
        code = item['code']
        process = item['process']
        norm = item['norm']
        total = item['total']
        damaged = item['damaged']
        note = item['note']
        overlaps = item['overlaps']
        start_dt, end_dt = item['interval']

        indices = [idx for idx, _ in overlaps]
        first = indices[0]
        total_overlap_hours = sum((hours for _, hours in overlaps), Decimal('0'))
        updated_by_id = _resolve_proxy_product_updated_by_id(
            track_manager_updates=track_manager_updates,
            user=user,
            report=report,
            product_id=item.get('product_id', -1),
            old_meta=old_meta,
            new_snap=_snapshot_from_prepared_proxy_item(item),
        )
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code=code,
            process_name=process,
            norm_per_hour=norm,
            status=ProductionShiftProduct.STATUS_DONE,
            submitted_locked=content_edit_only,
            sort_order=sort_order,
            first_slot_index=first,
            started_at=start_dt,
            ended_at=end_dt,
            total_quantity=total,
            total_damaged_quantity=damaged,
            completion_note=note[:500],
            updated_by_id=updated_by_id,
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

    if not content_edit_only and not preserve_draft:
        report.proxy_entered_by = user
    if not report.shift_started_at:
        report.shift_started_at = _slot_start_dt(report.report_date, slots[0])
    if content_edit_only or preserve_draft:
        report.status = prior_status
        report.submitted_at = prior_submitted_at
        report.submit_clicked_at = prior_submit_clicked_at
        if created and report.status == DailyWorkReport.STATUS_DRAFT:
            report.draft_saved_at = timezone.now()
    elif created:
        from reports.report_submit_time import resolve_submitted_at

        now = timezone.now()
        report.status = DailyWorkReport.STATUS_SUBMITTED
        report.submit_clicked_at = now
        report.submitted_at = resolve_submitted_at(report, now)
        report.auto_submitted = False
        lock_production_steps_on_submit(report)
    else:
        report.status = DailyWorkReport.STATUS_DRAFT
        report.auto_submitted = False
    report.save()

    if not content_edit_only and not preserve_draft and created:
        from reports.report_lock import auto_approve_fully_proxy_entered_report

        auto_approve_fully_proxy_entered_report(report)
    elif content_edit_only and created:
        from reports.report_lock import auto_approve_manager_edited_report

        auto_approve_manager_edited_report(report, user)

    from reports.models import DailyWorkReportEditLog
    from reports.report_edit_log import log_report_edit

    if content_edit_only:
        log_report_edit(
            report,
            user,
            summary=f'Chỉnh sửa nội dung ({created} công đoạn).',
            detail=change_detail,
        )
    elif preserve_draft:
        log_report_edit(
            report,
            user,
            summary=f'Quản lý chỉnh sửa báo cáo sai ({created} công đoạn).',
            detail=change_detail,
        )
    elif created:
        log_report_edit(
            report,
            user,
            action=DailyWorkReportEditLog.ACTION_SUBMIT,
            summary=f'Nhập hộ và nộp báo cáo ({created} công đoạn).',
            detail=collect_new_sessions_detail(report),
        )
    else:
        log_report_edit(report, user, summary='Lưu nhập hộ (chưa có dữ liệu).')

    return {'sessions': created}


@transaction.atomic
def add_production_session(
    report: DailyWorkReport,
    *,
    code: str,
    process: str,
    norm,
    total,
    damaged: int,
    note: str,
    start_time: str,
    end_time: str,
    updated_by=None,
):
    """
    Thêm 1 công đoạn mới theo kiểu nhập hộ (giờ bắt đầu/kết thúc).
    Dùng cho màn hình chỉnh sửa báo cáo đã nộp.
    """
    shift = _shift_for_report(report)
    slots = slots_for_shift(shift)
    slot_by_idx = {s.index: s for s in slots}
    sess = {
        'code': code,
        'process': process,
        'norm': norm,
        'total': total,
        'damaged': damaged,
        'note': note,
        'start_time': start_time,
        'end_time': end_time,
    }
    overlaps, interval = _proxy_session_overlaps(report.report_date, shift, sess, slot_by_idx)
    if not overlaps or not interval:
        raise ValueError('Giờ bắt đầu / kết thúc không hợp lệ hoặc nằm ngoài khung ca.')
    start_dt, end_dt = interval

    # Không cho chồng lấn; cho phép trùng biên (start == end cũ hoặc end == start cũ).
    existing = list(
        report.production_products.filter(
            started_at__isnull=False,
            ended_at__isnull=False,
        ).values('started_at', 'ended_at')
    )
    for row in existing:
        old_start = row['started_at']
        old_end = row['ended_at']
        if old_start is None or old_end is None:
            continue
        if start_dt < old_end and end_dt > old_start:
            raise ValueError(
                'Khoảng giờ bị chồng với công đoạn đã có. '
                'Có thể bắt đầu đúng bằng giờ kết thúc công đoạn trước.'
            )

    total_overlap_hours = sum((hours for _, hours in overlaps), Decimal('0'))
    next_sort = (
        report.production_products.aggregate(m=Max('sort_order')).get('m')
    )
    if next_sort is None:
        next_sort = -1
    indices = [idx for idx, _ in overlaps]
    first = indices[0]

    product = ProductionShiftProduct.objects.create(
        report=report,
        product_code=code.strip(),
        process_name=process.strip(),
        norm_per_hour=norm,
        status=ProductionShiftProduct.STATUS_DONE,
        submitted_locked=bool(report.status == DailyWorkReport.STATUS_SUBMITTED),
        sort_order=next_sort + 1,
        first_slot_index=first,
        started_at=start_dt,
        ended_at=end_dt,
        total_quantity=total,
        total_damaged_quantity=damaged,
        completion_note=(note or '').strip()[:500],
        updated_by=updated_by if updated_by and updated_by.id != report.employee_id else None,
    )

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
            note=(note or '').strip()[:500] if pos == 0 else '',
            partial_hours=partial,
            zero_reason='',
        )
    return product
