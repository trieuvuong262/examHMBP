from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cham_cong.forms import LeaveForm
from cham_cong.leave_calc import request_day_count
from cham_cong.leavebook import (
    annual_balance,
    annual_shortfall,
    conflicting_request,
    holiday_dates,
    span_hits_locked,
)
from cham_cong.models import LeaveRequest
from cham_cong.permissions import can_decide_for, can_punch, can_view_company
from cham_cong.services import team_user_ids, write_log
from cham_cong.views import _deny_punch
from hrm.permissions import format_direct_managers_label, get_profile


def _visible_requests(user):
    base = LeaveRequest.objects.select_related('user', 'user__profile', 'decided_by')
    if can_view_company(user):
        return base
    ids = team_user_ids(user)
    return base.filter(Q(user=user) | Q(user_id__in=ids))


def _mark_rows(rows, actor):
    review_ids = None if can_view_company(actor) else set(team_user_ids(actor))
    if not rows:
        return rows
    start = min(row.start_date for row in rows)
    end = max(row.end_date for row in rows)
    holidays = holiday_dates(start, end)
    for row in rows:
        row.day_count = request_day_count(row.start_date, row.end_date, row.kind, row.portion, holidays)
        row.can_decide = (
            row.status == LeaveRequest.STATUS_PENDING
            and row.user_id != actor.pk
            and (review_ids is None or row.user_id in review_ids)
        )
        row.can_cancel = row.status == LeaveRequest.STATUS_PENDING and row.user_id == actor.pk
    return rows


def _leave_error(user, item, exclude_pk=None):
    profile = get_profile(user)
    if not profile or not profile.is_employed:
        return 'Hồ sơ nhân sự chưa ở trạng thái đang làm.'
    if span_hits_locked(item.start_date, item.end_date):
        return 'Bảng công một tháng trong khoảng nghỉ đã khóa.'
    if item.kind == LeaveRequest.KIND_ANNUAL and profile.on_probation:
        return 'Đang thử việc nên chưa có phép năm. Có thể gửi nghỉ không lương hoặc nghỉ việc riêng.'
    conflict = conflicting_request(
        user, item.start_date, item.end_date, item.kind, item.portion, exclude_pk=exclude_pk,
    )
    if conflict:
        return f'Khoảng này trùng đơn nghỉ ngày {conflict.start_date:%d/%m/%Y}.'
    if item.kind == LeaveRequest.KIND_ANNUAL:
        missing = annual_shortfall(
            user, item.start_date, item.end_date, item.portion, exclude_pk=exclude_pk,
        )
        if missing:
            year, remaining, weight = missing[0]
            return (
                f'Phép năm {year} không đủ. Tính đến ngày nghỉ còn {remaining} ngày, '
                f'đơn này cần {weight} ngày.'
            )
    return None


@login_required
def leave_list(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    rows = list(_visible_requests(request.user)[:300])
    return render(request, 'cham_cong/leave_list.html', {
        'rows': _mark_rows(rows, request.user),
        'balance': annual_balance(request.user),
    })


@login_required
def leave_create(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    if request.method == 'POST':
        form = LeaveForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            error = _leave_error(request.user, item)
            if error:
                form.add_error(None, error)
            else:
                item.save()
                write_log(
                    request.user, 'leave_submit',
                    f'Gửi nghỉ {item.get_kind_display()} {item.start_date:%d/%m/%Y}',
                    request.user,
                )
                messages.success(request, 'Đã gửi đơn nghỉ. Quản lý trực tiếp sẽ duyệt.')
                return redirect('cham_cong:leaves')
    else:
        form = LeaveForm()
    return render(request, 'cham_cong/leave_form.html', {
        'form': form,
        'balance': annual_balance(request.user),
        'manager_label': format_direct_managers_label(request.user) or 'Nhân sự',
    })


@login_required
@require_POST
def leave_decide(request, pk):
    item = get_object_or_404(
        LeaveRequest.objects.select_related('user'),
        pk=pk, status=LeaveRequest.STATUS_PENDING,
    )
    if not can_decide_for(request.user, item.user):
        messages.error(request, 'Bạn không phải người duyệt đơn này.')
        return redirect('cham_cong:leaves')
    note = (request.POST.get('note') or '').strip()
    decision = request.POST.get('decision')
    if decision == 'reject':
        if not note:
            messages.error(request, 'Nhập lý do từ chối.')
            return redirect('cham_cong:leaves')
        item.status = LeaveRequest.STATUS_REJECTED
        item.decision_note = note
        item.decided_by = request.user
        item.decided_at = timezone.now()
        item.save()
        write_log(request.user, 'leave_reject', f'Từ chối nghỉ {item.start_date:%d/%m/%Y}', item.user)
        messages.success(request, 'Đã từ chối đơn nghỉ.')
        return redirect('cham_cong:leaves')
    if decision != 'approve':
        messages.error(request, 'Thao tác duyệt không hợp lệ.')
        return redirect('cham_cong:leaves')
    error = _leave_error(item.user, item, exclude_pk=item.pk)
    if error:
        messages.error(request, error)
        return redirect('cham_cong:leaves')
    item.status = LeaveRequest.STATUS_APPROVED
    item.decision_note = note
    item.decided_by = request.user
    item.decided_at = timezone.now()
    item.save()
    write_log(request.user, 'leave_approve', f'Duyệt nghỉ {item.start_date:%d/%m/%Y}', item.user)
    messages.success(request, 'Đã duyệt đơn nghỉ. Bảng công sẽ tính phép này, không sửa giờ chấm.')
    return redirect('cham_cong:leaves')


@login_required
@require_POST
def leave_cancel(request, pk):
    item = get_object_or_404(
        LeaveRequest, pk=pk, user=request.user, status=LeaveRequest.STATUS_PENDING,
    )
    item.status = LeaveRequest.STATUS_CANCELLED
    item.decided_at = timezone.now()
    item.save()
    write_log(request.user, 'leave_cancel', f'Hủy đơn nghỉ {item.start_date:%d/%m/%Y}', request.user)
    messages.success(request, 'Đã hủy đơn nghỉ.')
    return redirect('cham_cong:leaves')
