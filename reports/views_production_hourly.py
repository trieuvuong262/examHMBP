"""Báo cáo sản xuất — nhập sản lượng hàng giờ (mobile-first)."""

import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from hrm.permissions import (
    can_submit_daily_report,
    get_profile,
    get_team_report_members,
)
from reports.report_lock import (
    is_production_employee_edit_expired,
    production_edit_denied_message,
    production_employee_edit_deadline,
)
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    add_production_session,
    active_has_hourly_data,
    active_product,
    build_hourly_grid,
    build_proxy_entry_grid,
    can_edit_production_report,
    can_edit_production_norms,
    can_add_production_entry,
    can_resume_production_entry,
    can_operate_production_entry,
    can_proxy_enter_daily_report,
    complete_work_session,
    ensure_active_work_block,
    ensure_work_day_started,
    end_work_session,
    finalize_product_with_metadata,
    is_production_report_locked,
    is_production_entry_closed,
    lock_production_steps_on_submit,
    employee_can_edit_submitted_report_steps,
    report_steps_editable_for_viewer,
    product_is_submitted_locked,
    product_may_be_edited_by,
    production_server_now,
    viewer_may_edit_stage_time,
    parse_decimal,
    parse_non_negative_decimal,
    delete_production_products,
    resolve_declared_work_hours_for_save,
    validate_production_submit_efficiency,
    parse_int,
    save_hourly_entry,
    session_awaiting_completion,
    session_in_progress,
    shift_is_started,
    start_work_session,
    unfinalized_active_with_data,
    update_session_product,
)
from reports.production_shift_policy import (
    PRODUCTION_SHIFT_ORDER,
    build_shift_assignment_options,
    build_shift_picker_options,
    can_start_production_shift,
    is_production_shift_assignment_choice_required,
    production_reports_for_day,
    resolve_production_entry,
    shift_display_label,
)
from reports.production_slots import current_slot_index, slot_by_index
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()


def _parse_production_shift(request, *, report=None) -> str:
    from reports.production_slots import normalize_shift
    raw = (
        request.GET.get('shift')
        or request.POST.get('shift')
        or (report.shift if report and report.pk else '')
        or ''
    ).strip().upper()
    if not raw:
        return ''
    shift = normalize_shift(raw)
    if shift in PRODUCTION_SHIFT_ORDER:
        return shift
    return ''


def _hourly_grid_for_viewer(report, viewer, *, started: bool = True, steps_editable=None):
    if not report or not report.pk:
        return None
    if not started and not shift_is_started(report):
        return None
    if steps_editable is None:
        steps_editable = report_steps_editable_for_viewer(viewer, report)
    return build_hourly_grid(
        report,
        steps_editable=steps_editable,
    )


def _apply_review_payload(report, payload_str, *, relax_slot_scope=False, unlock_on_edit=False):
    """Cập nhật sản lượng từ JSON tổng kết (chỉnh sửa trên màn review / nhập hộ)."""
    try:
        rows = json.loads(payload_str or '[]')
    except json.JSONDecodeError:
        return False
    for row in rows:
        product_id = row.get('product_id')
        if not product_id:
            continue
        try:
            product = report.production_products.get(pk=product_id)
        except ProductionShiftProduct.DoesNotExist:
            continue
        if product_is_submitted_locked(product) and not unlock_on_edit:
            continue
        was_locked = product_is_submitted_locked(product)
        for cell in row.get('slots', []):
            slot_index = cell.get('slot_index')
            if slot_index is None:
                continue
            qty = parse_int(cell.get('quantity'))
            zero_reason = (cell.get('zero_reason') or '').strip()
            damaged_quantity = cell.get('damaged_quantity')
            if damaged_quantity not in (None, ''):
                damaged_quantity = parse_int(damaged_quantity)
            else:
                damaged_quantity = None
            note = cell.get('note')
            if note is not None:
                note = (note or '').strip()
            try:
                if qty > 0 or zero_reason:
                    save_hourly_entry(
                        product,
                        int(slot_index),
                        qty,
                        zero_reason=zero_reason,
                        damaged_quantity=damaged_quantity,
                        note=note,
                        relax_slot_scope=relax_slot_scope,
                    )
                else:
                    ProductionHourlyQuantity.objects.filter(
                        product=product,
                        slot_index=int(slot_index),
                    ).delete()
            except ValueError:
                return False
        if unlock_on_edit and was_locked:
            product.submitted_locked = False
            product.save(update_fields=['submitted_locked'])
    return True


def _resolve_production_subject(request, report_date):
    """NV đang nhập hoặc cấp trên nhập hộ (?for_user=)."""
    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    subject = request.user
    editing_for_other = False
    if for_user_id:
        try:
            target = get_team_report_members(request.user).get(pk=int(for_user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Không tìm thấy nhân viên cấp dưới.')
            return None, None, redirect('reports:team_cn')
        if can_proxy_enter_daily_report(request.user, target):
            subject = target
            editing_for_other = True
        else:
            shift = _parse_production_shift(request)
            report = _load_production_report(target, report_date, shift) if shift else None
            can_manager_edit = (
                report
                and report.pk
                and report.status == DailyWorkReport.STATUS_SUBMITTED
                and not report.hod_reviewed
                and can_edit_production_norms(request.user, report)
                and can_edit_production_report(
                    request.user,
                    report,
                    can_submit=can_submit_daily_report(request.user),
                )
            )
            if can_manager_edit:
                subject = target
                editing_for_other = True
            else:
                messages.error(request, 'Bạn không có quyền nhập báo cáo hộ nhân viên này.')
                return None, None, redirect('reports:team_cn')
    return subject, editing_for_other, None


def _load_production_report(subject, report_date, shift: str):
    from reports.views import _load_daily_report

    report = _load_daily_report(
        subject,
        report_date,
        report_profile=REPORT_PROFILE_PRODUCTION,
        shift=shift,
    )
    if report.pk:
        report = (
            DailyWorkReport.objects.prefetch_related(
                'production_products__hourly_entries',
            ).get(pk=report.pk)
        )
    return report


def _production_redirect(report_date, shift='', for_user_id=None, extra=None):
    url = f'{reverse("reports:today_cn")}?date={report_date.isoformat()}'
    if shift:
        url += f'&shift={shift}'
    if for_user_id:
        url += f'&for_user={for_user_id}'
    if extra:
        url += extra if extra.startswith('&') else f'&{extra}'
    return url


def _approve_after_manager_edit(request, report) -> None:
    """QL / tổ trưởng vừa sửa báo cáo đã nộp — chốt duyệt luôn."""
    from reports.report_lock import auto_approve_manager_edited_report

    if auto_approve_manager_edited_report(report, request.user):
        messages.info(request, 'Báo cáo đã chuyển sang trạng thái «Đã duyệt».')


def _is_content_edit_only(request, report) -> bool:
    if not report or not report.pk:
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    return (request.GET.get('edit_content') or request.POST.get('edit_content')) == '1'


def _is_edit_steps_mode(request, report) -> bool:
    """NV chủ động vào chế độ sửa báo cáo đã gửi (có nút Cập nhật báo cáo)."""
    if not report or not report.pk:
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return False
    return (request.GET.get('edit_steps') or request.POST.get('edit_steps')) == '1'


def _is_production_summary_editable(
    request,
    report,
    *,
    phase: str,
    proxy_mode: bool,
    content_edit_only: bool,
    can_edit: bool,
    is_locked: bool,
) -> bool:
    """Chỉ màn tổng kết có nút gửi/cập nhật mới cho sửa công đoạn."""
    if phase != 'review' or proxy_mode:
        return False
    if content_edit_only:
        return can_edit and not is_locked
    if not report or not report.pk:
        return False
    if report.status != DailyWorkReport.STATUS_SUBMITTED:
        return True
    if not can_edit or is_locked:
        return False
    return _is_edit_steps_mode(request, report)


def _from_detail_query(request) -> str:
    raw = (request.GET.get('from_detail') or request.POST.get('from_detail') or '').strip()
    if raw.isdigit():
        return f'&from_detail={raw}'
    return ''


def _content_edit_redirect_extra(request) -> str:
    return f'phase=review&edit_content=1{_from_detail_query(request)}'


def _review_redirect_extra(request, report, *, content_edit_only: bool = False) -> str:
    fd = _from_detail_query(request)
    if content_edit_only:
        return f'phase=review&edit_content=1{fd}'
    if report and report.pk and report.status == DailyWorkReport.STATUS_SUBMITTED:
        if _is_edit_steps_mode(request, report):
            return f'phase=review&edit_steps=1{fd}'
        return f'phase=review{fd}'
    return f'phase=review{fd}'


def _auto_resolve_shift_and_date(subject, report_date, *, explicit_shift: str = ''):
    """Tự nhận ca (sáng / tối) và ngày báo cáo theo giờ VPS."""
    if explicit_shift:
        return resolve_production_entry(
            subject,
            report_date,
            explicit_shift=explicit_shift,
        )
    return resolve_production_entry(subject, report_date)


def _prepare_production_report(subject, report_date, shift: str):
    """Tải hoặc tạo báo cáo ca — shift rỗng thì tự suy theo thời gian."""
    from reports.views import _ensure_daily_report_saved

    resolved_date, resolved_shift = _auto_resolve_shift_and_date(
        subject,
        report_date,
        explicit_shift=shift,
    )
    if not resolved_shift:
        return None, '', resolved_date, ''
    ok, reason = can_start_production_shift(subject, resolved_date, resolved_shift)
    existing = DailyWorkReport.objects.filter(
        employee=subject,
        report_date=resolved_date,
        report_profile=REPORT_PROFILE_PRODUCTION,
        shift=resolved_shift,
    ).first()
    if not ok and not existing:
        return None, reason, resolved_date, resolved_shift

    report = _load_production_report(subject, resolved_date, resolved_shift)
    report.shift = resolved_shift
    report = _ensure_daily_report_saved(report)
    return report, '', resolved_date, resolved_shift


def _handle_production_post(request, report, report_date, subject, editing_for_other, shift: str):
    """POST báo cáo SX — mốc bắt đầu/kết thúc công đoạn luôn lấy production_server_now() (VPS)."""
    from reports.views import _ensure_daily_report_saved, _finalize_report_submission

    action = request.POST.get('action', '')
    for_user = str(subject.id) if editing_for_other else ''
    content_edit_only = _is_content_edit_only(request, report)
    content_edit_extra = _content_edit_redirect_extra(request)

    if content_edit_only and action and action not in (
        'edit_session',
        'add_session',
        'delete_session',
        'update_declared_work_hours',
    ):
        messages.error(
            request,
            'Chỉ được sửa / thêm / xóa công đoạn hoặc thời gian làm việc trên màn chỉnh sửa báo cáo đã nộp.',
        )
        return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))

    if action == 'update_declared_work_hours':
        review_extra = _review_redirect_extra(request, report, content_edit_only=content_edit_only)
        from reports.production_hourly import viewer_may_edit_declared_work_hours

        if not viewer_may_edit_declared_work_hours(request.user, report):
            messages.warning(
                request,
                production_edit_denied_message(report, viewer=request.user)
                or 'Không thể sửa thời gian làm việc.',
            )
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        if report.status == DailyWorkReport.STATUS_SUBMITTED and (
            not content_edit_only and not _is_edit_steps_mode(request, report)
        ):
            messages.warning(request, 'Bấm «Sửa báo cáo» để chỉnh thời gian làm việc.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        before_hours = report.declared_work_hours
        work_hours, work_hours_err = resolve_declared_work_hours_for_save(
            report,
            request.POST.get('declared_work_hours'),
            allow_keep_existing=False,
        )
        if work_hours_err:
            messages.error(request, work_hours_err)
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        if before_hours == work_hours:
            messages.info(request, 'Thời gian làm việc không thay đổi.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        report.declared_work_hours = work_hours
        report.save(update_fields=['declared_work_hours', 'updated_at'])
        from reports.report_edit_log import log_report_edit

        before_txt = (
            str(before_hours).rstrip('0').rstrip('.')
            if before_hours is not None else '—'
        )
        after_txt = str(work_hours).rstrip('0').rstrip('.')
        log_report_edit(
            report,
            request.user,
            summary='Cập nhật thời gian làm việc.',
            detail=f'Trước: {before_txt} giờ\nSau: {after_txt} giờ',
        )
        messages.success(request, f'Đã cập nhật thời gian làm việc: {after_txt} giờ.')
        _approve_after_manager_edit(request, report)
        return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))

    if action == 'start_shift':
        if not (
            can_submit_daily_report(request.user)
            or (editing_for_other and can_proxy_enter_daily_report(request.user, subject))
        ):
            messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        start_shift = (request.POST.get('shift') or '').strip().upper()
        if start_shift not in PRODUCTION_SHIFT_ORDER:
            messages.error(request, 'Chọn ca làm hợp lệ.')
            return redirect(_production_redirect(report_date, '', for_user or None))
        report_date, start_shift = resolve_production_entry(
            subject,
            report_date,
            explicit_shift=start_shift,
        )
        ok, reason = can_start_production_shift(subject, report_date, start_shift)
        if not ok:
            messages.error(request, reason)
            return redirect(_production_redirect(report_date, '', for_user or None))
        report = _load_production_report(subject, report_date, start_shift)
        report.shift = start_shift
        report = _ensure_daily_report_saved(report)
        ensure_work_day_started(report)
        messages.success(request, f'Đã bắt đầu {shift_display_label(start_shift)}.')
        return redirect(_production_redirect(report_date, start_shift, for_user or None))

    if action == 'resume_production_entry':
        if not can_resume_production_entry(
            request.user,
            report,
            can_submit=can_submit_daily_report(request.user),
            is_proxy=editing_for_other,
        ):
            messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        if not report or not report.pk:
            return redirect(_production_redirect(report_date, shift, for_user or None))
        if not is_production_entry_closed(report):
            return redirect(_production_redirect(report_date, shift, for_user or None))
        report.status = DailyWorkReport.STATUS_DRAFT
        report.save(update_fields=['status', 'updated_at'])
        from reports.models import DailyWorkReportEditLog
        from reports.report_edit_log import log_report_edit

        log_report_edit(
            report,
            request.user,
            action=DailyWorkReportEditLog.ACTION_UPDATE,
            summary='Nhập tiếp báo cáo — thêm công đoạn mới.',
        )
        return redirect(_production_redirect(report_date, shift, for_user or None))

    if action == 'start_product':
        chosen_shift = _parse_production_shift(request, report=report) or shift
        if is_production_shift_assignment_choice_required() and not chosen_shift:
            messages.warning(request, 'Chọn ca sáng hoặc ca tối trước khi bắt đầu công đoạn.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        if is_production_entry_closed(report):
            messages.warning(
                request,
                'Báo cáo đã gửi — bấm «Nhập tiếp báo cáo» trên màn tổng kết để thêm công đoạn.',
            )
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=review'))
        if not can_add_production_entry(
            request.user,
            report,
            can_submit=can_submit_daily_report(request.user),
            is_proxy=editing_for_other,
        ):
            messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        report, err, report_date, shift = _prepare_production_report(
            subject, report_date, chosen_shift or shift,
        )
        if err:
            messages.error(request, err)
            return redirect(_production_redirect(report_date, shift, for_user or None))
        if not shift_is_started(report):
            ensure_work_day_started(report)
        try:
            start_work_session(report)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_production_redirect(report_date, shift, for_user or None))
        return redirect(_production_redirect(report_date, shift, for_user or None))

    if report and report.pk:
        report = DailyWorkReport.objects.get(pk=report.pk)

    _can_submit = can_submit_daily_report(request.user)
    can_edit = can_edit_production_report(
        request.user,
        report,
        can_submit=_can_submit,
        is_proxy=editing_for_other,
    )
    can_operate = can_operate_production_entry(
        request.user,
        report,
        can_submit=_can_submit,
        is_proxy=editing_for_other,
    )
    if action in ('end_product', 'complete_product', 'save', 'submit'):
        if not can_operate:
            if report and report.employee_id == request.user.id:
                messages.error(request, production_edit_denied_message(report, viewer=request.user))
            else:
                messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
            return redirect(_production_redirect(report_date, shift, subject.id if editing_for_other else None))
    elif action in ('edit_session', 'add_session', 'delete_session', 'save_review', 'finalize_product', 'save_hourly'):
        if not can_edit:
            if report and report.employee_id == request.user.id:
                messages.error(request, production_edit_denied_message(report, viewer=request.user))
            else:
                messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
            return redirect(_production_redirect(report_date, shift, subject.id if editing_for_other else None))

    if not report or not report.pk:
        report, err, report_date, shift = _prepare_production_report(
            subject, report_date, shift,
        )
        if err:
            messages.error(request, err)
            return redirect(_production_redirect(report_date, shift, for_user or None))

    report = _ensure_daily_report_saved(report)
    if not shift_is_started(report):
        ensure_work_day_started(report)

    if action == 'end_product':
        if is_production_entry_closed(report):
            messages.warning(request, 'Báo cáo đã gửi — không thể kết thúc thêm công đoạn.')
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=review'))
        ended = end_work_session(report)
        if not ended:
            messages.error(request, 'Không có công đoạn đang làm để kết thúc.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=complete_product'))

    if action == 'complete_product':
        if is_production_entry_closed(report):
            messages.warning(request, 'Báo cáo đã gửi — không thể nhập thêm sản lượng.')
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=review'))
        code = (request.POST.get('product_code') or '').strip()
        process = (request.POST.get('process_name') or '').strip()
        norm = parse_decimal(request.POST.get('norm_per_hour'))
        total_qty = parse_non_negative_decimal(request.POST.get('total_quantity'), default=Decimal('-1'))
        damaged_quantity = parse_int(request.POST.get('damaged_quantity'))
        note = (request.POST.get('note') or '').strip()
        zero_reason = (request.POST.get('zero_reason') or '').strip()
        if total_qty < 0:
            messages.error(request, 'Nhập sản lượng hợp lệ.')
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=complete_product'))
        if not session_awaiting_completion(report):
            messages.error(request, 'Không có công đoạn chờ hoàn tất.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        try:
            completed = complete_work_session(
                report,
                product_code=code,
                process_name=process,
                norm_per_hour=norm,
                total_quantity=total_qty,
                damaged_quantity=damaged_quantity,
                note=note,
                zero_reason=zero_reason,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=complete_product'))
        if completed:
            if total_qty == 0:
                messages.success(
                    request,
                    f'Đã ghi nhận công đoạn sản lượng 0 ({zero_reason[:80]}) — thời gian vẫn tính vào báo cáo.',
                )
            else:
                messages.success(request, f'Đã lưu {code} — tổng {total_qty.normalize()} sản phẩm.')
            from reports.report_edit_log import log_report_edit

            log_report_edit(
                report,
                request.user,
                summary=f'Hoàn tất công đoạn {(code or "—").strip()}.',
            )
        return redirect(_production_redirect(report_date, shift, for_user or None))

    if action == 'edit_session':
        product_id = parse_int(request.POST.get('product_id'), -1)
        review_extra = _review_redirect_extra(request, report, content_edit_only=content_edit_only)
        try:
            product = report.production_products.get(pk=product_id)
        except ProductionShiftProduct.DoesNotExist:
            messages.error(request, 'Không tìm thấy công đoạn cần sửa.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        if report.status == DailyWorkReport.STATUS_SUBMITTED and not content_edit_only and not _is_edit_steps_mode(request, report):
            messages.warning(request, 'Bấm «Sửa báo cáo» trên màn thống kê để chỉnh sửa công đoạn đã gửi.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        if not product_may_be_edited_by(
            request.user,
            report,
            product,
            content_edit_only=content_edit_only,
        ):
            denied = production_edit_denied_message(report, viewer=request.user)
            messages.warning(request, denied or 'Công đoạn này không thể sửa.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        code = (request.POST.get('product_code') or '').strip()
        process = (request.POST.get('process_name') or '').strip()
        norm = parse_decimal(request.POST.get('norm_per_hour'))
        total_qty = parse_non_negative_decimal(request.POST.get('total_quantity'), default=Decimal('-1'))
        damaged_quantity = parse_int(request.POST.get('damaged_quantity'))
        note = (request.POST.get('note') or '').strip()
        zero_reason = (request.POST.get('zero_reason') or '').strip()
        may_edit_time = viewer_may_edit_stage_time(
            request.user,
            report,
            product=product,
            for_wrong_stage=content_edit_only,
        )
        start_time = (request.POST.get('start_time') or '').strip() if may_edit_time else ''
        end_time = (request.POST.get('end_time') or '').strip() if may_edit_time else ''
        if total_qty < 0:
            messages.error(request, 'Nhập sản lượng hợp lệ.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        from reports.production_edit_log import (
            format_session_change_detail,
            snapshot_production_session,
        )

        before_snap = snapshot_production_session(product)
        try:
            update_session_product(
                product,
                product_code=code,
                process_name=process,
                norm_per_hour=norm,
                total_quantity=total_qty,
                damaged_quantity=damaged_quantity,
                note=note,
                zero_reason=zero_reason,
                start_time=start_time,
                end_time=end_time,
                updated_by=request.user,
                allow_edit_stage_time=may_edit_time,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        product.refresh_from_db()
        after_snap = snapshot_production_session(product)
        messages.success(
            request,
            f'Đã ghi nhận lý do sản lượng 0: {zero_reason[:120]}'
            if total_qty == 0
            else f'Đã cập nhật {code}.',
        )
        from reports.report_edit_log import log_report_edit

        log_report_edit(
            report,
            request.user,
            summary=f'Chỉnh sửa công đoạn {(code or product.product_code or "").strip() or "—"}.',
            detail=format_session_change_detail(before=before_snap, after=after_snap),
        )
        _approve_after_manager_edit(request, report)
        return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))

    if action == 'delete_session':
        product_id = parse_int(request.POST.get('product_id'), -1)
        review_extra = _review_redirect_extra(request, report, content_edit_only=content_edit_only)
        if product_id < 0:
            messages.error(request, 'Không tìm thấy công đoạn cần xóa.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        try:
            product = report.production_products.get(pk=product_id)
        except ProductionShiftProduct.DoesNotExist:
            messages.error(request, 'Không tìm thấy công đoạn cần xóa.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        if report.status == DailyWorkReport.STATUS_SUBMITTED and not content_edit_only and not _is_edit_steps_mode(request, report):
            messages.warning(request, 'Bấm «Sửa báo cáo» trên màn thống kê để chỉnh sửa công đoạn đã gửi.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        if not product_may_be_edited_by(
            request.user,
            report,
            product,
            content_edit_only=content_edit_only,
        ):
            denied = production_edit_denied_message(report, viewer=request.user)
            messages.warning(request, denied or 'Công đoạn này không thể xóa.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        label = (product.product_code or product.process_name or '—').strip() or '—'
        from reports.production_edit_log import (
            format_session_change_detail,
            snapshot_production_session,
        )

        before_snap = snapshot_production_session(product)
        deleted = delete_production_products(report, [product_id])
        if not deleted:
            messages.error(request, 'Không thể xóa công đoạn này.')
            return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))
        from reports.report_edit_log import log_report_edit

        log_report_edit(
            report,
            request.user,
            summary=f'Xóa công đoạn {label}.',
            detail=format_session_change_detail(before=before_snap),
        )
        messages.success(request, f'Đã xóa công đoạn {label}.')
        _approve_after_manager_edit(request, report)
        return redirect(_production_redirect(report_date, shift, for_user or None, review_extra))

    if action == 'add_session':
        if not content_edit_only:
            messages.error(request, 'Chỉ có thể thêm công đoạn ở màn chỉnh sửa báo cáo đã nộp.')
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=review'))
        if not viewer_may_edit_stage_time(request.user, report, for_wrong_stage=True):
            messages.error(request, 'Không được phép sửa thời gian công đoạn theo thiết lập chung.')
            return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))
        code = (request.POST.get('product_code') or '').strip()
        process = (request.POST.get('process_name') or '').strip()
        norm = parse_decimal(request.POST.get('norm_per_hour'))
        total_qty_raw = parse_decimal(request.POST.get('total_quantity'))
        damaged_quantity = parse_int(request.POST.get('damaged_quantity'))
        note = (request.POST.get('note') or '').strip()
        start_time = (request.POST.get('start_time') or '').strip()
        end_time = (request.POST.get('end_time') or '').strip()
        if not code or not process:
            messages.error(request, 'Điền mã hàng và tên công đoạn.')
            return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))
        if not norm or norm <= 0:
            messages.error(request, 'Định mức phải lớn hơn 0.')
            return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))
        if total_qty_raw is None or total_qty_raw < 0:
            messages.error(request, 'Nhập sản lượng hợp lệ.')
            return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))
        total_qty = total_qty_raw
        if not start_time or not end_time:
            messages.error(request, 'Chọn giờ bắt đầu và giờ kết thúc.')
            return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))
        try:
            product = add_production_session(
                report,
                code=code,
                process=process,
                norm=norm,
                total=total_qty,
                damaged=damaged_quantity,
                note=note,
                start_time=start_time,
                end_time=end_time,
                updated_by=request.user,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))
        from reports.production_edit_log import (
            format_session_change_detail,
            snapshot_production_session,
        )
        from reports.report_edit_log import log_report_edit

        after_snap = snapshot_production_session(product)
        log_report_edit(
            report,
            request.user,
            summary=f'Thêm công đoạn {(code or "—").strip()}.',
            detail=format_session_change_detail(after=after_snap),
        )
        messages.success(request, f'Đã thêm công đoạn {code}.')
        _approve_after_manager_edit(request, report)
        return redirect(_production_redirect(report_date, shift, for_user or None, content_edit_extra))

    if action == 'finalize_product':
        if is_production_entry_closed(report):
            messages.warning(request, 'Báo cáo đã gửi — không thể nhập thêm sản lượng.')
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=review'))
        code = (request.POST.get('product_code') or '').strip()
        process = (request.POST.get('process_name') or '').strip()
        norm = parse_decimal(request.POST.get('norm_per_hour'))
        active = active_product(report)
        if not active or not active_has_hourly_data(active):
            messages.error(request, 'Cần nhập ít nhất một sản lượng trước khi kết thúc mã hàng.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        if not code or not process or not norm or norm <= 0:
            messages.error(request, 'Điền đủ mã hàng, tên công đoạn và định mức > 0.')
            return redirect(_production_redirect(report_date, shift, for_user or None, 'phase=finish_product'))
        finalized = finalize_product_with_metadata(
            report,
            product_code=code,
            process_name=process,
            norm_per_hour=norm,
        )
        if finalized:
            messages.success(request, f'Đã kết thúc mã {code}. Tiếp tục nhập sản lượng.')
        return redirect(_production_redirect(report_date, shift, for_user or None))

    if action == 'save_hourly':
        if editing_for_other:
            product = ensure_active_work_block(report)
        else:
            messages.error(request, 'Chức năng nhập từng giờ chỉ dùng khi nhập hộ.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        slot_index = parse_int(request.POST.get('slot_index'), -1)
        qty = parse_int(request.POST.get('quantity'))
        zero_reason = (request.POST.get('zero_reason') or '').strip()
        damaged_raw = request.POST.get('damaged_quantity')
        damaged_quantity = parse_int(damaged_raw) if damaged_raw not in (None, '') else 0
        note = (request.POST.get('note') or '').strip()
        if slot_index < 0:
            messages.error(request, 'Khung giờ không hợp lệ.')
            return redirect(_production_redirect(report_date, shift, for_user or None))
        try:
            save_hourly_entry(
                product,
                slot_index,
                qty,
                zero_reason=zero_reason,
                damaged_quantity=damaged_quantity,
                note=note,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_production_redirect(report_date, shift, for_user or None))
        slot = slot_by_index(slot_index, shift)
        label = slot.label if slot else str(slot_index)
        if qty > 0:
            messages.success(request, f'Đã lưu {qty} — {label}.')
        else:
            messages.success(request, f'Đã ghi nhận sản lượng 0 — {label}.')
        return redirect(_production_redirect(report_date, shift, for_user or None))

    if action == 'save_review':
        relax = editing_for_other
        unlock_steps = (
            not editing_for_other
            and report.employee_id == request.user.id
            and employee_can_edit_submitted_report_steps(report)
        )
        if not _apply_review_payload(
            report,
            request.POST.get('review_json'),
            relax_slot_scope=relax,
            unlock_on_edit=unlock_steps,
        ):
            messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
            extra = 'phase=proxy' if editing_for_other else 'phase=review'
            return redirect(_production_redirect(report_date, shift, for_user or None, extra))
        messages.success(request, 'Đã lưu sản lượng.')
        report.draft_saved_at = timezone.now()
        report.save(update_fields=['draft_saved_at'])
        from reports.report_edit_log import log_report_edit

        log_report_edit(report, request.user, summary='Lưu sản lượng tổng kết.')
        extra = 'phase=proxy' if editing_for_other else 'phase=review'
        return redirect(_production_redirect(report_date, shift, for_user or None, extra))

    if action in ('save', 'submit'):
        if unfinalized_active_with_data(report):
            awaiting = session_awaiting_completion(report)
            in_progress = session_in_progress(report)
            if in_progress:
                messages.warning(
                    request,
                    'Còn công đoạn đang làm — bấm «Kết thúc» và nhập thông tin trước khi gửi.',
                )
            elif awaiting:
                messages.warning(
                    request,
                    'Còn công đoạn chưa nhập sản lượng — hoàn tất trước khi gửi.',
                )
            else:
                messages.warning(
                    request,
                    'Còn sản lượng chưa gắn mã hàng — điền thông tin mã hàng trước khi gửi.',
                )
            extra = 'phase=proxy' if editing_for_other else (
                'phase=complete_product' if awaiting else 'phase=working'
            )
            return redirect(_production_redirect(report_date, shift, for_user or None, extra))
        was_submitted = report.status == DailyWorkReport.STATUS_SUBMITTED
        if action == 'submit':
            review_json = request.POST.get('review_json')
            unlock_steps = (
                not editing_for_other
                and report.employee_id == request.user.id
                and employee_can_edit_submitted_report_steps(report)
            )
            if review_json:
                if not _apply_review_payload(
                    report,
                    review_json,
                    relax_slot_scope=editing_for_other,
                    unlock_on_edit=unlock_steps,
                ):
                    messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
                    extra = 'phase=proxy' if editing_for_other else 'phase=review'
                    return redirect(_production_redirect(report_date, shift, for_user or None, extra))
            grid = build_proxy_entry_grid(report) if editing_for_other else build_hourly_grid(report)
            if not grid.get('rows') or grid.get('grand_total', 0) <= 0:
                messages.error(request, 'Cần nhập ít nhất một mã hàng và sản lượng trước khi gửi.')
                extra = 'phase=proxy' if editing_for_other else 'phase=review'
                return redirect(_production_redirect(report_date, shift, for_user or None, extra))
            work_hours, work_hours_err = resolve_declared_work_hours_for_save(
                report,
                request.POST.get('declared_work_hours'),
                allow_keep_existing=was_submitted,
            )
            if work_hours_err:
                messages.error(request, work_hours_err)
                extra = 'phase=proxy' if editing_for_other else 'phase=review'
                return redirect(_production_redirect(report_date, shift, for_user or None, extra))
            report.declared_work_hours = work_hours
            _, efficiency_err = validate_production_submit_efficiency(
                report, declared_work_hours=work_hours,
            )
            if efficiency_err:
                if report.pk:
                    report.save(update_fields=['declared_work_hours', 'updated_at'])
                messages.error(request, efficiency_err)
                extra = 'phase=proxy' if editing_for_other else 'phase=review'
                return redirect(_production_redirect(report_date, shift, for_user or None, extra))
        report.report_profile = REPORT_PROFILE_PRODUCTION
        msg = _finalize_report_submission(report, action)
        if action == 'submit':
            lock_production_steps_on_submit(report)
        if action == 'submit' and was_submitted:
            msg = 'Đã cập nhật báo cáo.'
        messages.success(request, msg)
        report.save()
        from reports.models import DailyWorkReportEditLog
        from reports.report_edit_log import log_report_edit

        if action == 'submit':
            log_report_edit(
                report,
                request.user,
                action=(
                    DailyWorkReportEditLog.ACTION_RESUBMIT
                    if was_submitted
                    else DailyWorkReportEditLog.ACTION_SUBMIT
                ),
                summary='Cập nhật báo cáo đã nộp.' if was_submitted else 'Gửi báo cáo.',
            )
        if editing_for_other:
            return redirect('reports:detail_cn', pk=report.pk)
        return redirect(_production_redirect(report_date, shift, None, 'phase=review'))

    return None


def today_production_hourly(request, report_date, report_context_common):
    redirect_resp = _resolve_production_subject(request, report_date)
    if redirect_resp[2] is not None:
        return redirect_resp[2]
    subject, editing_for_other = redirect_resp[0], redirect_resp[1]
    user_profile = get_profile(subject)

    shift = _parse_production_shift(request)
    phase = (request.GET.get('phase') or '').strip().lower()
    force_picker = request.GET.get('pick_shift') == '1'
    report = None
    shift_choice_required = False
    shift_assignment_options = []

    can_edit = (
        can_submit_daily_report(request.user)
        or (editing_for_other and can_proxy_enter_daily_report(request.user, subject))
    )

    if request.method == 'POST':
        post_shift = _parse_production_shift(request)
        report, err, report_date, shift = _prepare_production_report(
            subject, report_date, post_shift,
        )
        if err and request.POST.get('action') != 'start_shift':
            messages.error(request, err)
            return redirect(_production_redirect(report_date, shift, subject.id if editing_for_other else None))
        result = _handle_production_post(
            request, report, report_date, subject, editing_for_other, shift,
        )
        if result:
            return result

    if phase == 'review' and not shift:
        report = production_reports_for_day(subject, report_date).order_by(
            '-submitted_at', '-updated_at',
        ).first()
        if report:
            report_date = report.report_date
            shift = report.shift
            report = _load_production_report(subject, report_date, shift)

    if explicit_shift := shift:
        requested_date = report_date
        report_date, shift = resolve_production_entry(
            subject, report_date, explicit_shift=explicit_shift,
        )
        # Ca tối qua 0h: URL có thể còn «hôm nay» — chuyển về ngày bắt đầu ca
        if (
            request.method == 'GET'
            and phase not in ('review',)
            and report_date != requested_date
        ):
            return redirect(
                _production_redirect(
                    report_date,
                    shift,
                    subject.id if editing_for_other else None,
                )
            )
        report = _load_production_report(subject, report_date, shift)
    elif force_picker and phase not in ('review',):
        shift_options = build_shift_picker_options(subject, report_date, can_edit=can_edit)
        ctx = report_context_common(request, report_date)
        ctx.update({
            'phase': 'select_shift',
            'shift_options': shift_options,
            'employee_name': (user_profile.full_name if user_profile else '') or subject.username,
            'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
            'subject_user': subject,
            'editing_for_other': editing_for_other,
            'for_user_param': subject.id if editing_for_other else '',
            'back_team_url': reverse('reports:team_cn') + f'?date={report_date.isoformat()}',
        })
        return render(request, 'reports/today_production_hourly.html', ctx)
    else:
        requested_date = report_date
        report_date, shift = resolve_production_entry(subject, report_date)
        if (
            request.method == 'GET'
            and phase not in ('review',)
            and shift
            and report_date != requested_date
        ):
            return redirect(
                _production_redirect(
                    report_date,
                    shift,
                    subject.id if editing_for_other else None,
                )
            )
        shift_choice_required = (
            not shift
            and is_production_shift_assignment_choice_required()
            and not editing_for_other
            and phase not in ('review', 'proxy')
        )
        if shift_choice_required:
            report = None
            err = ''
            shift_assignment_options = build_shift_assignment_options(subject, report_date)
        elif shift:
            ok, reason = can_start_production_shift(subject, report_date, shift)
            has_report = DailyWorkReport.objects.filter(
                employee=subject,
                report_date=report_date,
                report_profile=REPORT_PROFILE_PRODUCTION,
                shift=shift,
            ).exists()
            if not ok and not has_report:
                messages.error(request, reason)
                if editing_for_other:
                    shift_options = build_shift_picker_options(subject, report_date, can_edit=can_edit)
                    ctx = report_context_common(request, report_date)
                    ctx.update({
                        'phase': 'select_shift',
                        'shift_options': shift_options,
                        'employee_name': (user_profile.full_name if user_profile else '') or subject.username,
                        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
                        'subject_user': subject,
                        'editing_for_other': editing_for_other,
                        'for_user_param': subject.id if editing_for_other else '',
                        'back_team_url': reverse('reports:team_cn') + f'?date={report_date.isoformat()}',
                    })
                    return render(request, 'reports/today_production_hourly.html', ctx)
            report, err, report_date, shift = _prepare_production_report(subject, report_date, shift)
            if err:
                messages.error(request, err)
        else:
            report = None
            err = ''

    if report and report.pk:
        from reports.report_lock import ensure_production_report_approval_state

        if ensure_production_report_approval_state(report):
            report.refresh_from_db()
        _can_submit = can_submit_daily_report(request.user)
        can_edit = can_edit_production_report(
            request.user,
            report,
            can_submit=_can_submit,
            is_proxy=editing_for_other,
        )
        can_resume_entry = can_resume_production_entry(
            request.user,
            report,
            can_submit=_can_submit,
            is_proxy=editing_for_other,
        )
        can_add_entry = can_add_production_entry(
            request.user,
            report,
            can_submit=_can_submit,
            is_proxy=editing_for_other,
        )
    elif shift_choice_required:
        can_resume_entry = False
        can_add_entry = can_edit and not editing_for_other
    elif not can_edit:
        can_edit = False
        can_resume_entry = False
        can_add_entry = False
    else:
        can_resume_entry = False
        can_add_entry = False

    content_edit_only = _is_content_edit_only(request, report) if report and report.pk else False
    if content_edit_only:
        can_add_entry = False
        can_resume_entry = False
        phase = 'review'

    auto_shift_mode = not editing_for_other

    if report and report.pk and not auto_shift_mode and not shift_is_started(report) and (can_edit or can_add_entry) and phase not in ('review', 'proxy') and not content_edit_only:
        from reports.views import _ensure_daily_report_saved
        report = _ensure_daily_report_saved(report)
        ensure_work_day_started(report)
        report = _load_production_report(subject, report_date, shift)

    started = shift_is_started(report) if report and report.pk else False
    if auto_shift_mode and report and report.pk and (can_edit or can_add_entry) and phase not in ('review',):
        started = True
    is_submitted = bool(report and report.pk and report.status == DailyWorkReport.STATUS_SUBMITTED)
    is_locked = is_production_report_locked(report) if report and report.pk else False
    is_edit_expired = is_production_employee_edit_expired(report) if report and report.pk else False
    employee_edit_deadline = production_employee_edit_deadline(report) if report and report.pk else None

    if editing_for_other and (can_edit or can_add_entry) and report.pk and not started and not content_edit_only:
        from reports.views import _ensure_daily_report_saved
        report = _ensure_daily_report_saved(report)
        ensure_work_day_started(report)
        ensure_active_work_block(report)
        report = _load_production_report(subject, report_date, shift)
        started = True

    if is_submitted and phase not in ('review', 'proxy'):
        phase = 'review'

    proxy_mode = editing_for_other and not content_edit_only
    production_summary_editable = _is_production_summary_editable(
        request,
        report,
        phase=phase,
        proxy_mode=proxy_mode,
        content_edit_only=content_edit_only,
        can_edit=can_edit,
        is_locked=is_locked,
    )
    grid_steps_editable = (
        report_steps_editable_for_viewer(request.user, report)
        if production_summary_editable
        else False
    )

    current_product = active_product(report) if report and report.pk else None
    session_active = session_in_progress(report) if report and report.pk else None
    awaiting_product = session_awaiting_completion(report) if report and report.pk else None
    work_step = ''
    completed_sessions_count = 0
    if editing_for_other and not content_edit_only:
        if started:
            grid = build_proxy_entry_grid(report)
            if not grid.get('rows'):
                ensure_active_work_block(report)
                report = _load_production_report(subject, report_date, shift)
                grid = build_proxy_entry_grid(report)
        else:
            grid = None
        if phase in ('', 'working', 'hourly'):
            phase = 'proxy'
    elif editing_for_other and content_edit_only:
        grid = _hourly_grid_for_viewer(report, request.user, started=shift_is_started(report), steps_editable=grid_steps_editable)
    else:
        grid = _hourly_grid_for_viewer(report, request.user, started=started, steps_editable=grid_steps_editable)
        if not phase:
            if awaiting_product:
                phase = 'complete_product'
            else:
                phase = 'working'
        if phase == 'hourly':
            phase = 'working'

    if shift_choice_required and not editing_for_other:
        work_step = 'start'
        if phase in ('', 'hourly'):
            phase = 'working'
    elif not editing_for_other and started and phase not in ('review', 'proxy', 'select_shift'):
        if session_active:
            work_step = 'working'
        elif awaiting_product or phase == 'complete_product':
            work_step = 'complete'
            if phase != 'complete_product':
                phase = 'complete_product'
        elif not current_product:
            work_step = 'start'
        if grid and grid.get('rows'):
            completed_sessions_count = sum(
                1 for row in grid['rows'] if not row.get('is_unfinalized')
            )

    production_summary_editable = _is_production_summary_editable(
        request,
        report,
        phase=phase,
        proxy_mode=proxy_mode,
        content_edit_only=content_edit_only,
        can_edit=can_edit,
        is_locked=is_locked,
    )

    current_slot = current_slot_index(now=timezone.localtime(production_server_now()), report_date=report_date, shift=shift)
    has_unfinalized = bool(unfinalized_active_with_data(report)) if report and report.pk else False
    show_prod_submit = (
        phase == 'review'
        and not proxy_mode
        and not has_unfinalized
        and (
            (can_add_entry and not is_production_entry_closed(report))
            or (
                is_submitted
                and production_summary_editable
                and can_edit
                and not is_locked
            )
        )
    )
    production_edit_steps_url = ''
    production_stats_url = ''
    if (
        phase == 'review'
        and is_submitted
        and not production_summary_editable
        and can_edit
        and not is_locked
        and not proxy_mode
    ):
        production_edit_steps_url = _production_redirect(
            report_date,
            shift,
            subject.id if editing_for_other else None,
            f'phase=review&edit_steps=1{_from_detail_query(request)}',
        )
    elif (
        phase == 'review'
        and is_submitted
        and production_summary_editable
        and not content_edit_only
        and not proxy_mode
    ):
        production_stats_url = _production_redirect(
            report_date,
            shift,
            subject.id if editing_for_other else None,
            'phase=review',
        )

    if phase == 'review' and has_unfinalized and not editing_for_other:
        if awaiting_product:
            messages.info(
                request,
                'Còn công đoạn chưa nhập sản lượng — hoàn tất trước khi gửi báo cáo.',
            )
        else:
            messages.info(
                request,
                'Còn công đoạn chưa hoàn tất — xem bảng tổng bên dưới trước khi gửi.',
            )

    team_members = []
    if editing_for_other:
        team_members = list(
            get_team_report_members(request.user).select_related('profile').order_by('profile__full_name', 'username')
        )

    server_local_now = timezone.localtime(production_server_now())
    from_detail_pk = parse_int(request.GET.get('from_detail') or request.POST.get('from_detail'), -1)
    detail_pk = from_detail_pk if from_detail_pk > 0 else (report.pk if report and report.pk else None)
    ctx = report_context_common(request, report_date)
    ctx.update({
        'server_now': server_local_now,
        'server_now_display': server_local_now.strftime('%H:%M'),
        'server_date_display': server_local_now.strftime('%d/%m/%Y'),
        'report': report,
        'production_shift': shift,
        'production_shift_label': shift_display_label(shift) if shift else '',
        'employee_name': (user_profile.full_name if user_profile else '') or subject.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'subject_user': subject,
        'editing_for_other': editing_for_other,
        'can_edit': can_edit,
        'can_resume_entry': can_resume_entry,
        'can_add_entry': can_add_entry,
        'content_edit_only': content_edit_only,
        'is_submitted': is_submitted,
        'is_locked': is_locked,
        'production_entry_closed': is_production_entry_closed(report) if report and report.pk else False,
        'is_edit_expired': is_edit_expired,
        'employee_edit_deadline': employee_edit_deadline,
        'may_edit_stage_time': (
            viewer_may_edit_stage_time(
                request.user,
                report,
                for_wrong_stage=content_edit_only,
            )
            if report and report.pk
            else True
        ),
        'phase': phase,
        'shift_started': started,
        'current_product': current_product,
        'session_active': session_active,
        'awaiting_product': awaiting_product,
        'work_step': work_step,
        'completed_sessions_count': completed_sessions_count,
        'has_unfinalized': has_unfinalized,
        'pending_slots': [],
        'current_slot_index': current_slot,
        'current_slot_label': slot_by_index(current_slot, shift).label if current_slot is not None else '',
        'active_first_slot_label': (
            slot_by_index(current_product.first_slot_index, shift).label
            if current_product and slot_by_index(current_product.first_slot_index, shift)
            else ''
        ),
        'hourly_grid': grid,
        'proxy_mode': proxy_mode,
        'production_summary_editable': production_summary_editable,
        'production_summary_stats': (
            phase == 'review'
            and is_submitted
            and not production_summary_editable
            and not proxy_mode
        ),
        'show_prod_submit': show_prod_submit,
        'production_edit_steps_url': production_edit_steps_url,
        'production_stats_url': production_stats_url,
        'team_members': team_members,
        'for_user_param': subject.id if editing_for_other else '',
        'back_team_url': reverse('reports:team_cn') + f'?date={report_date.isoformat()}',
        'detail_url': reverse('reports:detail_cn', kwargs={'pk': detail_pk}) if detail_pk else '',
        'from_detail_param': str(from_detail_pk) if from_detail_pk > 0 else '',
        'shift_picker_url': _production_redirect(
            report_date, '', subject.id if editing_for_other else None, 'pick_shift=1',
        ),
        'production_review_url': (
            _production_redirect(report_date, shift, subject.id if editing_for_other else None, 'phase=review')
            if report and report.pk and started
            else ''
        ),
        'has_saved_product': bool(
            grid and any(not row.get('is_unfinalized') for row in grid.get('rows') or [])
        ),
        'shift_choice_required': shift_choice_required,
        'shift_assignment_options': shift_assignment_options,
    })
    return render(request, 'reports/today_production_hourly.html', ctx)
