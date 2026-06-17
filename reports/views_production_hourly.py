"""Báo cáo sản xuất — nhập sản lượng hàng giờ (mobile-first)."""

import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from hrm.permissions import (
    can_review_user_report,
    can_submit_daily_report,
    get_profile,
    get_report_team_users,
)
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    active_product,
    build_hourly_grid,
    can_edit_production_report,
    end_active_product,
    parse_decimal,
    parse_int,
    pending_slots_for_report,
    save_hourly_entry,
    shift_is_started,
    start_product_session,
    start_production_shift,
)
from reports.production_slots import current_slot_index, slot_by_index
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()


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
            return None, None, redirect('reports:team')
        if not can_review_user_report(request.user, DailyWorkReport(employee=target)):
            messages.error(request, 'Bạn không có quyền nhập báo cáo hộ nhân viên này.')
            return None, None, redirect('reports:team')
        subject = target
        editing_for_other = True
    return subject, editing_for_other, None


def _load_production_report(subject, report_date):
    from reports.views import _daily_report_defaults, _load_daily_report

    report = _load_daily_report(subject, report_date)
    if report.pk:
        report = (
            DailyWorkReport.objects.prefetch_related(
                'production_products__hourly_entries',
            ).get(pk=report.pk)
        )
    return report


def _production_redirect(report_date, for_user_id=None):
    url = f'{reverse("reports:today")}?date={report_date.isoformat()}'
    if for_user_id:
        url += f'&for_user={for_user_id}'
    return url


def _handle_production_post(request, report, report_date, subject, editing_for_other):
    from reports.views import _ensure_daily_report_saved, _finalize_report_submission

    can_edit = can_edit_production_report(
        request.user,
        report,
        can_submit=can_submit_daily_report(request.user),
        can_review=can_review_user_report(request.user, report),
    )
    if not can_edit:
        messages.error(request, 'Bạn không có quyền chỉnh sửa báo cáo này.')
        return redirect(_production_redirect(report_date, subject.id if editing_for_other else None))

    action = request.POST.get('action', '')
    report = _ensure_daily_report_saved(report)
    for_user = str(subject.id) if editing_for_other else ''

    if action == 'start_shift':
        shift = request.POST.get('shift') or DailyWorkReport.SHIFT_MORNING
        start_production_shift(report, shift)
        messages.success(request, 'Đã bắt đầu ca làm việc. Nhập mã hàng đầu tiên.')
        return redirect(_production_redirect(report_date, for_user or None))

    if action == 'start_product':
        code = (request.POST.get('product_code') or '').strip()
        process = (request.POST.get('process_name') or '').strip()
        norm = parse_decimal(request.POST.get('norm_per_hour'))
        if not code or not process or not norm or norm <= 0:
            messages.error(request, 'Điền đủ mã hàng, tên công đoạn và định mức > 0.')
            return redirect(_production_redirect(report_date, for_user or None))
        start_product_session(
            report,
            product_code=code,
            process_name=process,
            norm_per_hour=norm,
        )
        messages.success(request, f'Đã bắt đầu mã {code}.')
        return redirect(_production_redirect(report_date, for_user or None))

    if action == 'save_hourly':
        product = active_product(report)
        if not product:
            messages.error(request, 'Chưa có mã hàng đang làm.')
            return redirect(_production_redirect(report_date, for_user or None))
        slot_index = parse_int(request.POST.get('slot_index'), -1)
        qty = parse_int(request.POST.get('quantity'))
        partial = parse_decimal(request.POST.get('partial_hours'))
        if slot_index < 0:
            messages.error(request, 'Khung giờ không hợp lệ.')
            return redirect(_production_redirect(report_date, for_user or None))
        save_hourly_entry(product, slot_index, qty, partial_hours=partial)
        slot = slot_by_index(slot_index)
        label = slot.label if slot else str(slot_index)
        messages.success(request, f'Đã lưu {qty} — {label}.')
        return redirect(_production_redirect(report_date, for_user or None))

    if action == 'end_product':
        ended = end_active_product(report)
        if ended:
            messages.info(request, f'Đã kết thúc mã {ended.product_code}. Nhập mã hàng tiếp theo.')
        else:
            messages.warning(request, 'Không có mã hàng đang làm.')
        return redirect(_production_redirect(report_date, for_user or None))

    if action == 'end_shift':
        end_active_product(report)
        return redirect(_production_redirect(report_date, for_user or None) + '&phase=review')

    if action == 'save_review':
        payload = request.POST.get('review_json') or '[]'
        try:
            rows = json.loads(payload)
        except json.JSONDecodeError:
            messages.error(request, 'Dữ liệu tổng kết không hợp lệ.')
            return redirect(_production_redirect(report_date, for_user or None) + '&phase=review')
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
                if qty > 0:
                    save_hourly_entry(product, int(slot_index), qty, partial_hours=partial)
                else:
                    ProductionHourlyQuantity.objects.filter(
                        product=product,
                        slot_index=int(slot_index),
                    ).delete()
        messages.success(request, 'Đã cập nhật tổng kết.')
        report.draft_saved_at = timezone.now()
        report.save(update_fields=['draft_saved_at'])
        return redirect(_production_redirect(report_date, for_user or None) + '&phase=review')

    if action in ('save', 'submit'):
        if action == 'submit':
            grid = build_hourly_grid(report)
            if not grid.get('rows') or grid.get('grand_total', 0) <= 0:
                messages.error(request, 'Cần nhập ít nhất một mã hàng và sản lượng trước khi gửi.')
                return redirect(_production_redirect(report_date, for_user or None) + '&phase=review')
        msg = _finalize_report_submission(report, action)
        messages.success(request, msg)
        report.report_profile = REPORT_PROFILE_PRODUCTION
        report.save()
        if editing_for_other:
            return redirect('reports:detail', pk=report.pk)
        return redirect(_production_redirect(report_date))

    return None


def today_production_hourly(request, report_date, report_context_common):
    redirect_resp = _resolve_production_subject(request, report_date)
    if redirect_resp[2] is not None:
        return redirect_resp[2]
    subject, editing_for_other = redirect_resp[0], redirect_resp[1]

    report = _load_production_report(subject, report_date)
    user_profile = get_profile(subject)

    if request.method == 'POST':
        result = _handle_production_post(
            request, report, report_date, subject, editing_for_other,
        )
        if result:
            return result

    phase = (request.GET.get('phase') or '').strip().lower()
    started = shift_is_started(report)
    current_product = active_product(report)
    pending = pending_slots_for_report(report) if started and current_product else []
    current_slot = current_slot_index(report_date=report_date)
    grid = build_hourly_grid(report) if started else None

    if not phase:
        if not started:
            phase = 'idle'
        elif not current_product:
            phase = 'need_product'
        elif pending:
            phase = 'hourly'
        else:
            phase = 'working'

    can_edit = can_edit_production_report(
        request.user,
        report,
        can_submit=can_submit_daily_report(request.user),
        can_review=can_review_user_report(request.user, report),
    )

    ctx = report_context_common(request, report_date)
    ctx.update({
        'report': report,
        'report_period': 'daily',
        'employee_name': (user_profile.full_name if user_profile else '') or subject.username,
        'department_name': user_profile.department.name if user_profile and user_profile.department_id else '',
        'subject_user': subject,
        'editing_for_other': editing_for_other,
        'can_edit': can_edit,
        'phase': phase,
        'shift_started': started,
        'current_product': current_product,
        'pending_slots': pending,
        'current_slot_index': current_slot,
        'current_slot_label': slot_by_index(current_slot).label if current_slot is not None else '',
        'hourly_grid': grid,
        'shift_choices': DailyWorkReport.SHIFT_CHOICES,
        'for_user_param': subject.id if editing_for_other else '',
        'back_team_url': reverse('reports:team') + f'?date={report_date.isoformat()}',
        'detail_url': reverse('reports:detail', kwargs={'pk': report.pk}) if report.pk else '',
    })
    return render(request, 'reports/today_production_hourly.html', ctx)
