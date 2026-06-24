"""Báo cáo sản xuất — nhập sản lượng hàng giờ (mobile-first)."""

import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from hrm.permissions import (
    can_submit_daily_report,
    get_profile,
    get_report_team_users,
)
from reports.report_lock import is_report_edit_expired, report_edit_denied_message
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    active_has_hourly_data,
    active_product,
    build_hourly_grid,
    build_proxy_entry_grid,
    can_edit_production_report,
    can_proxy_enter_daily_report,
    ensure_active_work_block,
    ensure_work_day_started,
    finalize_product_with_metadata,
    is_production_report_locked,
    parse_decimal,
    parse_int,
    pending_slots_for_report,
    save_hourly_entry,
    shift_is_started,
    unfinalized_active_with_data,
)
from reports.production_shift_policy import (
    PRODUCTION_SHIFT_ORDER,
    build_shift_picker_options,
    can_start_production_shift,
    shift_display_label,
)
from reports.production_slots import current_slot_index, slot_by_index
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()


def _parse_production_shift(request, *, report=None) -> str:
    raw = (
        request.GET.get('shift')
        or request.POST.get('shift')
        or (report.shift if report and report.pk else '')
        or ''
    ).strip().upper()
    if raw in PRODUCTION_SHIFT_ORDER:
        return raw
    return ''


def _apply_review_payload(report, payload_str, *, relax_slot_scope=False):
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
        for cell in row.get('slots', []):
            slot_index = cell.get('slot_index')
            if slot_index is None:
                continue
            qty = parse_int(cell.get('quantity'))
            partial = parse_decimal(cell.get('partial_hours'))
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
                        partial_hours=partial,
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
    return True


def _resolve_production_subject(request, report_date):
    """NV đang nhập hoặc cấp trên nhập hộ (?for_user=)."""
    for_user_id = request.GET.get('for_user') or request.POST.get('for_user')
    subject = request.user
    editing_for_other = False
    if for_user_id:
        try:
            target = get_report_team_users(request.user).get(pk=int(for_user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Không tìm thấy nhân viên cấp dưới.')
            return None, None, redirect('reports:team_cn')
        if not can_proxy_enter_daily_report(request.user, target):
            messages.error(request, 'Bạn không có quyền nhập báo cáo hộ nhân viên này.')
            return None, None, redirect('reports:team_cn')
        subject = target
        editing_for_other = True
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


def _handle_production_post(request, report, report_date, subject, editing_for_other, shift: str):
    from reports.views import _ensure_daily_report_saved, _finalize_report_submission

    if report.pk:
        report = DailyWorkReport.objects.get(pk=report.pk)

    can_edit = can_edit_production_report(
        request.user,
        report,
        can_submit=can_submit_daily_report(request.user),
        is_proxy=editing_for_other,
    )
    if not can_edit:
        if report.employee_id == request.user.id:
            messages.error(request, report_edit_denied_message(report))
        else:
            messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
        return redirect(_production_redirect(report_date, shift, subject.id if editing_for_other else None))

    action = request.POST.get('action', '')
    for_user = str(subject.id) if editing_for_other else ''

    if action == 'start_shift':
        start_shift = (request.POST.get('shift') or '').strip().upper()
        if start_shift not in PRODUCTION_SHIFT_ORDER:
            messages.error(request, 'Chọn ca làm hợp lệ.')
            return redirect(_production_redirect(report_date, '', for_user or None))
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

    if not report.pk:
        messages.error(request, 'Chọn ca làm trước khi nhập báo cáo.')
        return redirect(_production_redirect(report_date, '', for_user or None))

    report = _ensure_daily_report_saved(report)
    if not shift_is_started(report):
        ensure_work_day_started(report)

    if action == 'finalize_product':
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
        product = ensure_active_work_block(report)
        slot_index = parse_int(request.POST.get('slot_index'), -1)
        qty = parse_int(request.POST.get('quantity'))
        partial = parse_decimal(request.POST.get('partial_hours'))
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
                partial_hours=partial,
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
        if not _apply_review_payload(
            report,
            request.POST.get('review_json'),
            relax_slot_scope=relax,
        ):
            messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
            extra = 'phase=proxy' if editing_for_other else 'phase=review'
            return redirect(_production_redirect(report_date, shift, for_user or None, extra))
        messages.success(request, 'Đã lưu sản lượng.')
        report.draft_saved_at = timezone.now()
        report.save(update_fields=['draft_saved_at'])
        extra = 'phase=proxy' if editing_for_other else 'phase=review'
        return redirect(_production_redirect(report_date, shift, for_user or None, extra))

    if action in ('save', 'submit'):
        if unfinalized_active_with_data(report):
            messages.warning(
                request,
                'Còn sản lượng chưa gắn mã hàng — điền thông tin mã hàng trước khi gửi.',
            )
            extra = 'phase=proxy' if editing_for_other else 'phase=finish_product'
            return redirect(_production_redirect(report_date, shift, for_user or None, extra))
        if action == 'submit':
            review_json = request.POST.get('review_json')
            if review_json:
                if not _apply_review_payload(
                    report,
                    review_json,
                    relax_slot_scope=editing_for_other,
                ):
                    messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
                    extra = 'phase=proxy' if editing_for_other else 'phase=review'
                    return redirect(_production_redirect(report_date, shift, for_user or None, extra))
            grid = build_proxy_entry_grid(report) if editing_for_other else build_hourly_grid(report)
            if not grid.get('rows') or grid.get('grand_total', 0) <= 0:
                messages.error(request, 'Cần nhập ít nhất một mã hàng và sản lượng trước khi gửi.')
                extra = 'phase=proxy' if editing_for_other else 'phase=review'
                return redirect(_production_redirect(report_date, shift, for_user or None, extra))
        was_submitted = report.status == DailyWorkReport.STATUS_SUBMITTED
        msg = _finalize_report_submission(report, action)
        if action == 'submit' and was_submitted:
            msg = 'Đã cập nhật báo cáo.'
        messages.success(request, msg)
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
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
    report = _load_production_report(subject, report_date, shift) if shift else None

    can_edit = False
    if report and report.pk:
        can_edit = can_edit_production_report(
            request.user,
            report,
            can_submit=can_submit_daily_report(request.user),
            is_proxy=editing_for_other,
        )
    else:
        can_edit = (
            can_submit_daily_report(request.user)
            or (editing_for_other and can_proxy_enter_daily_report(request.user, subject))
        )

    if request.method == 'POST':
        if not report:
            post_shift = _parse_production_shift(request) or DailyWorkReport.SHIFT_MORNING
            report = _load_production_report(subject, report_date, post_shift)
            shift = post_shift
        result = _handle_production_post(
            request, report, report_date, subject, editing_for_other, shift,
        )
        if result:
            return result

    phase = (request.GET.get('phase') or '').strip().lower()

    if not shift:
        if phase not in ('review', 'proxy'):
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
        shift = DailyWorkReport.SHIFT_MORNING
        report = _load_production_report(subject, report_date, shift)

    if not report.pk:
        ok, reason = can_start_production_shift(subject, report_date, shift)
        if not ok:
            messages.error(request, reason)
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
        if phase not in ('review', 'proxy', 'working', 'hourly'):
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

    can_edit = can_edit_production_report(
        request.user,
        report,
        can_submit=can_submit_daily_report(request.user),
        is_proxy=editing_for_other,
    )

    if report.pk and not shift_is_started(report) and can_edit and phase not in ('review', 'proxy'):
        from reports.views import _ensure_daily_report_saved
        report = _ensure_daily_report_saved(report)
        ensure_work_day_started(report)
        report = _load_production_report(subject, report_date, shift)

    started = shift_is_started(report)
    is_submitted = report.status == DailyWorkReport.STATUS_SUBMITTED
    is_locked = is_production_report_locked(report)
    is_edit_expired = is_report_edit_expired(report)

    if editing_for_other and can_edit and report.pk and not started:
        from reports.views import _ensure_daily_report_saved
        report = _ensure_daily_report_saved(report)
        ensure_work_day_started(report)
        ensure_active_work_block(report)
        report = _load_production_report(subject, report_date, shift)
        started = True

    if is_submitted and phase not in ('review', 'proxy'):
        phase = 'review'

    current_product = active_product(report) if report.pk else None
    if editing_for_other:
        pending = []
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
    else:
        pending = pending_slots_for_report(report) if started else []
        grid = build_hourly_grid(report) if started else None
        if not phase:
            if pending:
                phase = 'hourly'
            else:
                phase = 'working'

    current_slot = current_slot_index(report_date=report_date, shift=shift)
    has_unfinalized = bool(unfinalized_active_with_data(report)) if report.pk else False

    if phase == 'review' and has_unfinalized and not editing_for_other:
        messages.info(
            request,
            'Còn sản lượng chưa gắn mã hàng — xem bảng tổng bên dưới và bấm «Hoàn tất mã hàng» trước khi gửi.',
        )

    team_members = []
    if editing_for_other:
        team_members = list(
            get_report_team_users(request.user).select_related('profile').order_by('profile__full_name', 'username')
        )

    ctx = report_context_common(request, report_date)
    ctx.update({
        'report': report,
        'production_shift': shift,
        'production_shift_label': shift_display_label(shift),
        'employee_name': (user_profile.full_name if user_profile else '') or subject.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'subject_user': subject,
        'editing_for_other': editing_for_other,
        'can_edit': can_edit,
        'is_submitted': is_submitted,
        'is_locked': is_locked,
        'is_edit_expired': is_edit_expired,
        'phase': phase,
        'shift_started': started,
        'current_product': current_product,
        'has_unfinalized': has_unfinalized,
        'pending_slots': pending,
        'current_slot_index': current_slot,
        'current_slot_label': slot_by_index(current_slot, shift).label if current_slot is not None else '',
        'active_first_slot_label': (
            slot_by_index(current_product.first_slot_index, shift).label
            if current_product and slot_by_index(current_product.first_slot_index, shift)
            else ''
        ),
        'hourly_grid': grid,
        'proxy_mode': editing_for_other,
        'team_members': team_members,
        'for_user_param': subject.id if editing_for_other else '',
        'back_team_url': reverse('reports:team_cn') + f'?date={report_date.isoformat()}',
        'detail_url': reverse('reports:detail_cn', kwargs={'pk': report.pk}) if report.pk else '',
        'shift_picker_url': _production_redirect(report_date, '', subject.id if editing_for_other else None),
    })
    return render(request, 'reports/today_production_hourly.html', ctx)
