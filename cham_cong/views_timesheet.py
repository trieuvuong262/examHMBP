from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from decimal import Decimal

from cham_cong.forms import AdjustmentForm
from cham_cong.leavebook import leave_totals
from cham_cong.models import AttendanceAdjustment, AttendanceDay, LeaveRequest, TimesheetPeriod
from cham_cong.permissions import (
    MENU_PUNCH,
    MODULE_CHAM_CONG,
    can_configure,
    can_decide_for,
    can_punch,
    can_view_company,
)
from cham_cong.services import (
    apply_classification,
    month_is_locked,
    resolve_shift,
    stamp_event_time,
    team_user_ids,
    write_log,
)
from cham_cong.timesheet import month_bounds, parse_day, parse_month, rows_for_users, summarize_days, week_bounds
from cham_cong.views import _deny_punch, _locked_day
from hrm.menu_permissions import handle_menu_access_denied


def _scope_users(user):
    base = User.objects.filter(is_active=True, profile__is_employed=True).select_related(
        'profile', 'profile__department',
    )
    if can_view_company(user):
        return base.order_by('profile__full_name', 'username')
    ids = team_user_ids(user)
    return base.filter(Q(pk=user.pk) | Q(pk__in=ids)).order_by('profile__full_name', 'username')


def _mark_decisions(rows, actor):
    review_ids = None if can_view_company(actor) else set(team_user_ids(actor))
    for row in rows:
        row.can_decide = (
            row.status == AttendanceAdjustment.STATUS_PENDING
            and row.user_id != actor.pk
            and (review_ids is None or row.user_id in review_ids)
        )
    return rows


@login_required
def timesheet(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    today = timezone.localdate()
    view = request.GET.get('view') or 'month'
    if view not in ('month', 'week', 'day'):
        view = 'month'
    year, month, month_text = parse_month(request.GET.get('month'), today)
    day = parse_day(request.GET.get('day'), today)
    if view == 'week':
        start, end = week_bounds(day)
    elif view == 'day':
        start = end = day
    else:
        start, end = month_bounds(year, month)
        day = today if start <= today <= end else start

    users = list(_scope_users(request.user)[:500])
    person_id = (request.GET.get('person') or '').strip()
    person = None
    if person_id.isdigit():
        person = next((item for item in users if item.pk == int(person_id)), None)
    daily = []
    person_leaves = []
    if person or len(users) == 1:
        person = person or users[0]
        daily = list(
            AttendanceDay.objects.filter(user=person, work_date__gte=start, work_date__lte=end)
            .select_related('shift')
            .order_by('work_date')
        )
        person_leaves = list(LeaveRequest.objects.filter(
            user=person, status=LeaveRequest.STATUS_APPROVED,
            start_date__lte=end, end_date__gte=start,
        ).order_by('start_date'))
    period = TimesheetPeriod.objects.filter(year=year, month=month).first()
    adjustments = AttendanceAdjustment.objects.filter(
        user__in=users, work_date__gte=start, work_date__lte=end,
    ).select_related('user', 'user__profile', 'decided_by')
    leave_by_user = leave_totals([user.pk for user in users], start, end)
    rows = rows_for_users(users, start, end, leave_by_user)
    totals = summarize_days(AttendanceDay.objects.filter(
        user__in=users, work_date__gte=start, work_date__lte=end,
    ))
    totals['leave_days'] = sum((row['leave_days'] for row in rows), Decimal('0'))
    totals['unpaid_days'] = sum((row['unpaid_days'] for row in rows), Decimal('0'))
    return render(request, 'cham_cong/timesheet.html', {
        'view': view,
        'month': month_text,
        'day': day,
        'start': start,
        'end': end,
        'rows': rows,
        'totals': totals,
        'person': person,
        'daily': daily,
        'person_leaves': person_leaves,
        'period': period,
        'month_locked': bool(period and period.is_locked),
        'adjustments': _mark_decisions(list(adjustments[:100]), request.user),
        'can_lock': can_configure(request.user),
        'focus_year': year,
        'focus_month': month,
    })


@login_required
def adjustment_create(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    shift = resolve_shift(request.user)
    day_value = parse_day(request.GET.get('ngay') or request.POST.get('work_date'), None)
    existing = None
    if day_value:
        existing = AttendanceDay.objects.filter(user=request.user, work_date=day_value).first()
    if request.method == 'POST':
        form = AdjustmentForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            error = _adjustment_error(item, shift)
            if error:
                form.add_error(None, error)
            else:
                item.save()
                write_log(
                    request.user, 'adjustment_submit',
                    f'Xin chỉnh công {item.work_date:%d/%m/%Y}', request.user,
                )
                messages.success(request, 'Đã gửi yêu cầu chỉnh sửa. Quản lý trực tiếp sẽ duyệt.')
                return redirect('cham_cong:timesheet')
    else:
        initial = {}
        if existing and existing.clock_in:
            initial = {
                'work_date': existing.work_date,
                'clock_in_time': timezone.localtime(existing.clock_in).time().replace(microsecond=0),
                'clock_out_time': (
                    timezone.localtime(existing.clock_out).time().replace(microsecond=0)
                    if existing.clock_out else None
                ),
                'break_out_time': (
                    timezone.localtime(existing.break_out).time().replace(microsecond=0)
                    if existing.break_out else None
                ),
                'break_in_time': (
                    timezone.localtime(existing.break_in).time().replace(microsecond=0)
                    if existing.break_in else None
                ),
            }
        elif day_value:
            initial = {'work_date': day_value}
        form = AdjustmentForm(initial=initial)
    return render(request, 'cham_cong/adjustment_form.html', {
        'form': form,
        'shift': shift,
        'existing': existing,
    })


def _adjustment_error(item, shift):
    if month_is_locked(item.work_date):
        return 'Bảng công tháng này đã khóa.'
    if not shift:
        return 'Bạn chưa được gán ca.'
    clock_in = stamp_event_time(item.work_date, item.clock_in_time, shift)
    clock_out = stamp_event_time(item.work_date, item.clock_out_time, shift)
    if clock_out <= clock_in:
        return 'Giờ ra phải sau giờ vào.'
    day = AttendanceDay.objects.filter(user=item.user, work_date=item.work_date).first()
    if not day or not day.clock_in:
        return 'Ngày này chưa có giờ vào. Hãy dùng đơn bổ sung công.'
    if AttendanceAdjustment.objects.filter(
        user=item.user, work_date=item.work_date, status=AttendanceAdjustment.STATUS_PENDING,
    ).exists():
        return 'Ngày này đang có yêu cầu chỉnh sửa chờ duyệt.'
    return None


@login_required
@require_POST
def adjustment_decide(request, pk):
    item = get_object_or_404(
        AttendanceAdjustment.objects.select_related('user'),
        pk=pk, status=AttendanceAdjustment.STATUS_PENDING,
    )
    if not can_decide_for(request.user, item.user):
        messages.error(request, 'Bạn không phải người duyệt yêu cầu này.')
        return redirect('cham_cong:timesheet')
    note = (request.POST.get('note') or '').strip()
    decision = request.POST.get('decision')
    if decision == 'reject':
        if not note:
            messages.error(request, 'Nhập lý do từ chối.')
            return redirect('cham_cong:timesheet')
        item.status = AttendanceAdjustment.STATUS_REJECTED
        item.decision_note = note
        item.decided_by = request.user
        item.decided_at = timezone.now()
        item.save()
        write_log(request.user, 'adjustment_reject', f'Từ chối chỉnh công {item.work_date:%d/%m/%Y}', item.user)
        messages.success(request, 'Đã từ chối yêu cầu chỉnh sửa.')
        return redirect('cham_cong:timesheet')
    if decision != 'approve':
        messages.error(request, 'Thao tác duyệt không hợp lệ.')
        return redirect('cham_cong:timesheet')
    if month_is_locked(item.work_date):
        messages.error(request, 'Bảng công tháng này đã khóa.')
        return redirect('cham_cong:timesheet')
    shift = resolve_shift(item.user)
    if not shift:
        messages.error(request, 'Nhân viên chưa được gán ca.')
        return redirect('cham_cong:timesheet')
    clock_in = stamp_event_time(item.work_date, item.clock_in_time, shift)
    clock_out = stamp_event_time(item.work_date, item.clock_out_time, shift)
    if clock_out <= clock_in:
        messages.error(request, 'Giờ ra trên yêu cầu không sau giờ vào.')
        return redirect('cham_cong:timesheet')
    with transaction.atomic():
        day = _locked_day(item.user, item.work_date)
        day.clock_in = clock_in
        day.clock_out = clock_out
        day.in_method = day.in_method or AttendanceDay.METHOD_MANUAL
        day.out_method = AttendanceDay.METHOD_MANUAL
        if item.break_out_time and item.break_in_time:
            day.break_out = stamp_event_time(item.work_date, item.break_out_time, shift)
            day.break_in = stamp_event_time(item.work_date, item.break_in_time, shift)
        else:
            day.break_out = None
            day.break_in = None
        day.shift = day.shift or shift
        day.source = AttendanceDay.SOURCE_ADJUSTMENT
        apply_classification(day, shift)
        day.save()
        item.status = AttendanceAdjustment.STATUS_APPROVED
        item.decision_note = note
        item.decided_by = request.user
        item.decided_at = timezone.now()
        item.save()
    write_log(request.user, 'adjustment_approve', f'Duyệt chỉnh công {item.work_date:%d/%m/%Y}', item.user)
    messages.success(request, 'Đã duyệt và cập nhật bảng công.')
    return redirect('cham_cong:timesheet')


@login_required
@require_POST
def timesheet_lock(request):
    if not can_configure(request.user):
        if can_punch(request.user):
            messages.error(request, 'Chỉ nhân sự được khóa bảng công tháng.')
            return redirect('cham_cong:timesheet')
        return handle_menu_access_denied(request, MODULE_CHAM_CONG, MENU_PUNCH)
    today = timezone.localdate()
    year, month, _text = parse_month(request.POST.get('month'), today)
    period, _created = TimesheetPeriod.objects.get_or_create(year=year, month=month)
    lock = request.POST.get('action') == 'lock'
    period.is_locked = lock
    period.locked_by = request.user
    period.locked_at = timezone.now()
    period.save()
    action = 'timesheet_lock' if lock else 'timesheet_unlock'
    label = 'Khóa' if lock else 'Mở khóa'
    write_log(request.user, action, f'{label} bảng công {month:02d}/{year}')
    messages.success(request, f'Đã {label.lower()} bảng công tháng {month:02d}/{year}.')
    return redirect(f"{reverse('cham_cong:timesheet')}?month={year:04d}-{month:02d}")
