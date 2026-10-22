from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cham_cong.forms import SupplementForm
from cham_cong.models import AttendanceDay, AttendanceSupplement, WorkSite
from cham_cong.permissions import (
    MENU_PUNCH,
    MENU_SUPPLEMENTS,
    MODULE_CHAM_CONG,
    can_configure,
    can_decide_for,
    can_punch,
    can_view_company,
)
from cham_cong.services import (
    apply_classification,
    current_work_date,
    detected_ip_label,
    month_is_locked,
    open_attendance,
    resolve_shift,
    should_force_punch,
    stamp_event_time,
    team_user_ids,
    verify_location,
    visible_attendance,
    write_log,
)
from hrm.menu_permissions import handle_menu_access_denied
from hrm.permissions import format_direct_managers_label


def _deny_punch(request):
    return handle_menu_access_denied(request, MODULE_CHAM_CONG, MENU_PUNCH)


def _locked_day(user, work_date):
    day = (
        AttendanceDay.objects.select_for_update()
        .filter(user=user, work_date=work_date)
        .first()
    )
    if day:
        return day
    try:
        return AttendanceDay.objects.create(user=user, work_date=work_date)
    except IntegrityError:
        return AttendanceDay.objects.select_for_update().get(user=user, work_date=work_date)


def _stamp_location(day, location, prefix):
    method = location['method']
    setattr(day, f'{prefix}_method', method)
    setattr(day, f'{prefix}_ip', location.get('ip') or '')
    if method == AttendanceDay.METHOD_GPS:
        setattr(day, f'{prefix}_lat', location['latitude'])
        setattr(day, f'{prefix}_lng', location['longitude'])
        setattr(day, f'{prefix}_distance_m', location['distance_m'])
    if prefix == 'in' or not day.site_id:
        day.site = location['site']


@login_required
def punch(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    if request.method == 'POST':
        return _punch_post(request)

    user = request.user
    shift = resolve_shift(user)
    record = open_attendance(user)
    work_date = current_work_date(user)
    if record is None:
        record = (
            AttendanceDay.objects.filter(user=user, work_date=work_date)
            .select_related('shift', 'site')
            .first()
        )
    sites_exist = WorkSite.objects.filter(is_active=True).exists()
    ip_ready = False
    if sites_exist:
        preview, _error = verify_location(request)
        ip_ready = preview is not None
    month_text = (request.GET.get('month') or timezone.localdate().strftime('%Y-%m')).strip()
    try:
        year, month = (int(part) for part in month_text.split('-', 1))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = timezone.localdate().year, timezone.localdate().month
        month_text = f'{year:04d}-{month:02d}'
    history = AttendanceDay.objects.filter(
        user=user, work_date__year=year, work_date__month=month,
    ).select_related('shift', 'site').order_by('-work_date')
    return render(request, 'cham_cong/punch.html', {
        'shift': shift,
        'record': record,
        'work_date': work_date,
        'ip_label': detected_ip_label(request),
        'ip_ready': ip_ready,
        'sites_exist': sites_exist,
        'force_block': should_force_punch(user),
        'can_configure': can_configure(user),
        'month': month_text,
        'history': history[:62],
    })


def _punch_post(request):
    action = request.POST.get('action')
    if action not in ('in', 'out', 'break_out', 'break_in'):
        messages.error(request, 'Thao tác chấm công không hợp lệ.')
        return redirect('cham_cong:punch')

    user = request.user
    shift = resolve_shift(user)
    if action == 'in' and not shift:
        messages.error(request, 'Bạn chưa được gán ca. Liên hệ nhân sự.')
        return redirect('cham_cong:punch')

    location, error = verify_location(
        request, request.POST.get('latitude'), request.POST.get('longitude'),
    )
    if error:
        messages.error(request, error)
        return redirect('cham_cong:punch')

    now = timezone.now()
    work_probe = current_work_date(user, now) if action == 'in' else None
    with transaction.atomic():
        if action == 'in':
            work_date = work_probe
            if month_is_locked(work_date):
                messages.error(request, 'Bảng công tháng này đã khóa.')
                return redirect('cham_cong:punch')
            day = _locked_day(user, work_date)
            if day.clock_in:
                messages.info(request, 'Hôm nay bạn đã chấm vào.')
                return redirect('cham_cong:punch')
            day.clock_in = now
            day.source = AttendanceDay.SOURCE_LIVE
            _stamp_location(day, location, 'in')
            apply_classification(day, shift)
            day.save()
            write_log(user, 'clock_in', f'Chấm vào {timezone.localtime(now):%H:%M %d/%m/%Y}', user)
            messages.success(request, 'Đã chấm công vào.')
            return redirect('cham_cong:punch')

        day = (
            AttendanceDay.objects.select_for_update()
            .filter(user=user, clock_in__isnull=False, clock_out__isnull=True)
            .order_by('-work_date')
            .first()
        )
        if not day:
            messages.error(request, 'Chưa có giờ vào để chấm ra hoặc nghỉ giữa ca.')
            return redirect('cham_cong:punch')
        if month_is_locked(day.work_date):
            messages.error(request, 'Bảng công tháng này đã khóa.')
            return redirect('cham_cong:punch')
        shift = day.shift or shift
        if action == 'out':
            if now <= day.clock_in:
                messages.error(request, 'Giờ ra phải sau giờ vào.')
                return redirect('cham_cong:punch')
            day.clock_out = now
            _stamp_location(day, location, 'out')
            message = 'Đã chấm công ra.'
            log_action = 'clock_out'
        elif action == 'break_out':
            if day.break_out:
                messages.info(request, 'Bạn đã bấm ra nghỉ giữa ca.')
                return redirect('cham_cong:punch')
            day.break_out = now
            message = 'Đã ghi nhận ra nghỉ giữa ca.'
            log_action = 'break_out'
        else:
            if not day.break_out:
                messages.error(request, 'Bấm ra nghỉ giữa ca trước khi vào lại.')
                return redirect('cham_cong:punch')
            if day.break_in:
                messages.info(request, 'Bạn đã bấm vào lại.')
                return redirect('cham_cong:punch')
            if now <= day.break_out:
                messages.error(request, 'Giờ vào lại phải sau giờ ra nghỉ.')
                return redirect('cham_cong:punch')
            day.break_in = now
            message = 'Đã ghi nhận vào lại sau nghỉ.'
            log_action = 'break_in'
        apply_classification(day, shift)
        day.save()
        write_log(user, log_action, message, user)
    messages.success(request, message)
    return redirect('cham_cong:punch')


@login_required
def history(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    month_text = (request.GET.get('month') or timezone.localdate().strftime('%Y-%m')).strip()
    try:
        year, month = (int(part) for part in month_text.split('-', 1))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = timezone.localdate().year, timezone.localdate().month
        month_text = f'{year:04d}-{month:02d}'

    rows = visible_attendance(request.user).filter(
        work_date__year=year, work_date__month=month,
    ).select_related('user', 'user__profile', 'shift', 'site')
    return render(request, 'cham_cong/history.html', {
        'rows': rows[:500],
        'month': month_text,
        'can_filter_people': can_view_company(request.user) or bool(team_user_ids(request.user)),
    })


@login_required
def supplement_list(request):
    if not can_punch(request.user):
        return handle_menu_access_denied(request, MODULE_CHAM_CONG, MENU_SUPPLEMENTS)
    if can_view_company(request.user):
        rows = AttendanceSupplement.objects.all()
    else:
        ids = team_user_ids(request.user)
        rows = AttendanceSupplement.objects.filter(user_id__in=[request.user.pk, *ids])
    rows = list(rows.select_related('user', 'user__profile', 'decided_by', 'decided_by__profile')[:300])
    review_ids = None if can_view_company(request.user) else set(team_user_ids(request.user))
    for row in rows:
        row.can_decide = (
            row.status == AttendanceSupplement.STATUS_PENDING
            and row.user_id != request.user.pk
            and (review_ids is None or row.user_id in review_ids)
        )
    return render(request, 'cham_cong/supplement_list.html', {'rows': rows})


@login_required
def supplement_create(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    shift = resolve_shift(request.user)
    if request.method == 'POST':
        form = SupplementForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            error = _supplement_conflict(item, shift)
            if error:
                form.add_error(None, error)
            else:
                item.save()
                write_log(
                    request.user,
                    'supplement_submit',
                    f'Gửi bổ sung công {item.work_date:%d/%m/%Y}',
                    request.user,
                )
                messages.success(request, 'Đã gửi đơn bổ sung. Quản lý trực tiếp sẽ duyệt.')
                return redirect('cham_cong:supplements')
    else:
        form = SupplementForm()
    return render(request, 'cham_cong/supplement_form.html', {
        'form': form,
        'shift': shift,
        'manager_label': format_direct_managers_label(request.user) or 'Nhân sự',
    })


def _supplement_conflict(item, shift):
    if month_is_locked(item.work_date):
        return 'Bảng công tháng này đã khóa.'
    if not shift:
        return 'Bạn chưa được gán ca nên chưa gửi bổ sung được.'
    clock_in = stamp_event_time(item.work_date, item.clock_in_time, shift)
    clock_out = stamp_event_time(item.work_date, item.clock_out_time, shift)
    if clock_out <= clock_in:
        return 'Giờ ra phải sau giờ vào.'
    if AttendanceSupplement.objects.filter(
        user=item.user, work_date=item.work_date, status=AttendanceSupplement.STATUS_PENDING,
    ).exists():
        return 'Ngày này đang có đơn bổ sung chờ duyệt.'
    day = AttendanceDay.objects.filter(user=item.user, work_date=item.work_date).first()
    if day and day.clock_in and day.clock_out:
        return 'Ngày này đã đủ giờ vào và giờ ra.'
    return None


@login_required
@require_POST
def supplement_decide(request, pk):
    item = get_object_or_404(
        AttendanceSupplement.objects.select_related('user'),
        pk=pk,
        status=AttendanceSupplement.STATUS_PENDING,
    )
    if not can_decide_for(request.user, item.user):
        messages.error(request, 'Bạn không phải người duyệt đơn này.')
        return redirect('cham_cong:supplements')
    decision = request.POST.get('decision')
    note = (request.POST.get('note') or '').strip()
    if decision == 'reject':
        if not note:
            messages.error(request, 'Nhập lý do từ chối.')
            return redirect('cham_cong:supplements')
        item.status = AttendanceSupplement.STATUS_REJECTED
        item.decision_note = note
        item.decided_by = request.user
        item.decided_at = timezone.now()
        item.save()
        write_log(request.user, 'supplement_reject', f'Từ chối bổ sung {item.work_date:%d/%m/%Y}', item.user)
        messages.success(request, 'Đã từ chối đơn.')
        return redirect('cham_cong:supplements')
    if decision != 'approve':
        messages.error(request, 'Thao tác duyệt không hợp lệ.')
        return redirect('cham_cong:supplements')
    if month_is_locked(item.work_date):
        messages.error(request, 'Bảng công tháng này đã khóa.')
        return redirect('cham_cong:supplements')

    shift = resolve_shift(item.user)
    if not shift:
        messages.error(request, 'Nhân viên chưa được gán ca.')
        return redirect('cham_cong:supplements')
    clock_in = stamp_event_time(item.work_date, item.clock_in_time, shift)
    clock_out = stamp_event_time(item.work_date, item.clock_out_time, shift)
    if clock_out <= clock_in:
        messages.error(request, 'Giờ ra trên đơn không sau giờ vào.')
        return redirect('cham_cong:supplements')

    with transaction.atomic():
        day = _locked_day(item.user, item.work_date)
        if day.clock_in and day.clock_out:
            messages.error(request, 'Ngày này đã đủ công, không ghi đè.')
            return redirect('cham_cong:supplements')
        if not day.clock_in:
            day.clock_in = clock_in
            day.in_method = AttendanceDay.METHOD_MANUAL
        day.clock_out = clock_out
        day.out_method = AttendanceDay.METHOD_MANUAL
        if item.break_out_time and item.break_in_time:
            day.break_out = stamp_event_time(item.work_date, item.break_out_time, shift)
            day.break_in = stamp_event_time(item.work_date, item.break_in_time, shift)
        day.source = AttendanceDay.SOURCE_SUPPLEMENT
        apply_classification(day, shift)
        day.save()
        item.status = AttendanceSupplement.STATUS_APPROVED
        item.decision_note = note
        item.decided_by = request.user
        item.decided_at = timezone.now()
        item.save()
    write_log(request.user, 'supplement_approve', f'Duyệt bổ sung {item.work_date:%d/%m/%Y}', item.user)
    messages.success(request, 'Đã duyệt và ghi vào ngày công.')
    return redirect('cham_cong:supplements')
