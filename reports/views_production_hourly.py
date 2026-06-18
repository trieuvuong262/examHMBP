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
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    active_has_hourly_data,
    active_product,
    build_hourly_grid,
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
from reports.production_slots import current_slot_index, slot_by_index
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()


def _apply_review_payload(report, payload_str):
    """Cập nhật sản lượng từ JSON tổng kết (chỉnh sửa trên màn review)."""
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
            try:
                if qty > 0 or zero_reason:
                    save_hourly_entry(
                        product,
                        int(slot_index),
                        qty,
                        partial_hours=partial,
                        zero_reason=zero_reason,
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


def _load_production_report(subject, report_date):
    from reports.views import _load_daily_report

    report = _load_daily_report(subject, report_date, report_profile=REPORT_PROFILE_PRODUCTION)
    if report.pk:
        report = (
            DailyWorkReport.objects.prefetch_related(
                'production_products__hourly_entries',
            ).get(pk=report.pk)
        )
    return report


def _production_redirect(report_date, for_user_id=None, extra=None):
    url = f'{reverse("reports:today_cn")}?date={report_date.isoformat()}'
    if for_user_id:
        url += f'&for_user={for_user_id}'
    if extra:
        url += extra if extra.startswith('&') else f'&{extra}'
    return url


def _handle_production_post(request, report, report_date, subject, editing_for_other):
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
        if is_production_report_locked(report) and report.employee_id == request.user.id:
            messages.error(request, 'Cấp trên đã xem báo cáo — không thể chỉnh sửa.')
            return redirect(_production_redirect(report_date, None, 'phase=review'))
        messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
        return redirect(_production_redirect(report_date, subject.id if editing_for_other else None))

    action = request.POST.get('action', '')
    report = _ensure_daily_report_saved(report)
    ensure_work_day_started(report)
    for_user = str(subject.id) if editing_for_other else ''

    if action == 'finalize_product':
        code = (request.POST.get('product_code') or '').strip()
        process = (request.POST.get('process_name') or '').strip()
        norm = parse_decimal(request.POST.get('norm_per_hour'))
        active = active_product(report)
        if not active or not active_has_hourly_data(active):
            messages.error(request, 'Cần nhập ít nhất một sản lượng trước khi kết thúc mã hàng.')
            return redirect(_production_redirect(report_date, for_user or None))
        if not code or not process or not norm or norm <= 0:
            messages.error(request, 'Điền đủ mã hàng, tên công đoạn và định mức > 0.')
            return redirect(_production_redirect(report_date, for_user or None, 'phase=finish_product'))
        finalized = finalize_product_with_metadata(
            report,
            product_code=code,
            process_name=process,
            norm_per_hour=norm,
        )
        if finalized:
            messages.success(request, f'Đã kết thúc mã {code}. Tiếp tục nhập sản lượng.')
        return redirect(_production_redirect(report_date, for_user or None))

    if action == 'save_hourly':
        product = ensure_active_work_block(report)
        slot_index = parse_int(request.POST.get('slot_index'), -1)
        qty = parse_int(request.POST.get('quantity'))
        partial = parse_decimal(request.POST.get('partial_hours'))
        zero_reason = (request.POST.get('zero_reason') or '').strip()
        if slot_index < 0:
            messages.error(request, 'Khung giờ không hợp lệ.')
            return redirect(_production_redirect(report_date, for_user or None))
        try:
            save_hourly_entry(
                product,
                slot_index,
                qty,
                partial_hours=partial,
                zero_reason=zero_reason,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_production_redirect(report_date, for_user or None))
        slot = slot_by_index(slot_index)
        label = slot.label if slot else str(slot_index)
        if qty > 0:
            messages.success(request, f'Đã lưu {qty} — {label}.')
        else:
            messages.success(request, f'Đã ghi nhận sản lượng 0 — {label}.')
        return redirect(_production_redirect(report_date, for_user or None))

    if action == 'save_review':
        if not _apply_review_payload(report, request.POST.get('review_json')):
            messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
            return redirect(_production_redirect(report_date, for_user or None, 'phase=review'))
        messages.success(request, 'Đã cập nhật tổng kết.')
        report.draft_saved_at = timezone.now()
        report.save(update_fields=['draft_saved_at'])
        return redirect(_production_redirect(report_date, for_user or None, 'phase=review'))

    if action in ('save', 'submit'):
        if unfinalized_active_with_data(report):
            messages.warning(
                request,
                'Còn sản lượng chưa gắn mã hàng — bấm «Kết thúc mã hàng» và điền thông tin trước khi gửi.',
            )
            return redirect(_production_redirect(report_date, for_user or None, 'phase=finish_product'))
        if action == 'submit':
            review_json = request.POST.get('review_json')
            if review_json:
                if not _apply_review_payload(report, review_json):
                    messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
                    return redirect(_production_redirect(report_date, for_user or None, 'phase=review'))
            grid = build_hourly_grid(report)
            if not grid.get('rows') or grid.get('grand_total', 0) <= 0:
                messages.error(request, 'Cần nhập ít nhất một mã hàng và sản lượng trước khi gửi.')
                return redirect(_production_redirect(report_date, for_user or None, 'phase=review'))
        was_submitted = report.status == DailyWorkReport.STATUS_SUBMITTED
        msg = _finalize_report_submission(report, action)
        if action == 'submit' and was_submitted:
            msg = 'Đã cập nhật báo cáo.'
        messages.success(request, msg)
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
        if editing_for_other:
            return redirect('reports:detail_cn', pk=report.pk)
        return redirect(_production_redirect(report_date, None, 'phase=review'))

    return None


def today_production_hourly(request, report_date, report_context_common):
    redirect_resp = _resolve_production_subject(request, report_date)
    if redirect_resp[2] is not None:
        return redirect_resp[2]
    subject, editing_for_other = redirect_resp[0], redirect_resp[1]

    report = _load_production_report(subject, report_date)
    user_profile = get_profile(subject)

    can_edit = can_edit_production_report(
        request.user,
        report,
        can_submit=can_submit_daily_report(request.user),
        is_proxy=editing_for_other,
    )

    if request.method == 'POST':
        result = _handle_production_post(
            request, report, report_date, subject, editing_for_other,
        )
        if result:
            return result
    elif can_edit and not shift_is_started(report):
        from reports.views import _ensure_daily_report_saved
        report = _ensure_daily_report_saved(report)
        ensure_work_day_started(report)
        report = _load_production_report(subject, report_date)

    phase = (request.GET.get('phase') or '').strip().lower()
    started = shift_is_started(report)
    is_submitted = report.status == DailyWorkReport.STATUS_SUBMITTED
    is_locked = is_production_report_locked(report)

    if is_submitted and phase not in ('review',):
        phase = 'review'

    current_product = active_product(report)
    pending = pending_slots_for_report(report) if started else []
    current_slot = current_slot_index(report_date=report_date)
    grid = build_hourly_grid(report) if started else None
    has_unfinalized = bool(unfinalized_active_with_data(report))

    if phase == 'review' and has_unfinalized:
        messages.info(
            request,
            'Còn sản lượng chưa gắn mã hàng — xem bảng tổng bên dưới và bấm «Hoàn tất mã hàng» trước khi gửi.',
        )

    if not phase:
        if pending:
            phase = 'hourly'
        else:
            phase = 'working'

    ctx = report_context_common(request, report_date)
    ctx.update({
        'report': report,
        'report_period': 'daily',
        'employee_name': (user_profile.full_name if user_profile else '') or subject.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'subject_user': subject,
        'editing_for_other': editing_for_other,
        'can_edit': can_edit,
        'is_submitted': is_submitted,
        'is_locked': is_locked,
        'phase': phase,
        'shift_started': started,
        'current_product': current_product,
        'has_unfinalized': has_unfinalized,
        'pending_slots': pending,
        'current_slot_index': current_slot,
        'current_slot_label': slot_by_index(current_slot).label if current_slot is not None else '',
        'active_first_slot_label': (
            slot_by_index(current_product.first_slot_index).label
            if current_product and slot_by_index(current_product.first_slot_index)
            else ''
        ),
        'hourly_grid': grid,
        'for_user_param': subject.id if editing_for_other else '',
        'back_team_url': reverse('reports:team_cn') + f'?date={report_date.isoformat()}',
        'detail_url': reverse('reports:detail_cn', kwargs={'pk': report.pk}) if report.pk else '',
    })
    return render(request, 'reports/today_production_hourly.html', ctx)
