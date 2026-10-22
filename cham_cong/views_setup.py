from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cham_cong.forms import AssignmentForm, HolidayForm, PolicyForm, ShiftForm, SiteForm
from cham_cong.hr_report import monthly_attendance_report
from cham_cong.payrollbook import fund_report, payroll_fund
from cham_cong.models import (
    AttendanceLog,
    AttendancePolicy,
    Holiday,
    Shift,
    ShiftAssignment,
    WorkSite,
    WorkSiteIp,
)
from cham_cong.permissions import MENU_PUNCH, MODULE_CHAM_CONG, can_configure, can_punch
from cham_cong.services import write_log
from hrm.menu_permissions import handle_menu_access_denied


def _config_required(request):
    if can_configure(request.user):
        return None
    if can_punch(request.user):
        messages.error(request, 'Chỉ nhân sự được sửa ca, lịch và địa điểm.')
        return redirect('cham_cong:punch')
    return handle_menu_access_denied(request, MODULE_CHAM_CONG, MENU_PUNCH)


@login_required
def schedule(request):
    denied = _config_required(request)
    if denied:
        return denied
    return render(request, 'cham_cong/schedule.html', {
        'shifts': Shift.objects.all(),
        'assignments': ShiftAssignment.objects.filter(is_active=True).select_related(
            'shift', 'department', 'division', 'user', 'user__profile',
        ),
        'holidays': Holiday.objects.all()[:100],
        'holiday_form': HolidayForm(),
        'assignment_form': AssignmentForm(),
    })


@login_required
def shift_edit(request, pk=None):
    denied = _config_required(request)
    if denied:
        return denied
    shift = get_object_or_404(Shift, pk=pk) if pk else Shift()
    if request.method == 'POST':
        form = ShiftForm(request.POST, instance=shift)
        if form.is_valid():
            saved = form.save()
            write_log(request.user, 'shift_save', f'Lưu ca {saved.name}')
            messages.success(request, 'Đã lưu ca làm việc.')
            return redirect('cham_cong:schedule')
    else:
        form = ShiftForm(instance=shift)
    return render(request, 'cham_cong/shift_form.html', {'form': form, 'shift': shift})


@login_required
@require_POST
def assignment_save(request):
    denied = _config_required(request)
    if denied:
        return denied
    form = AssignmentForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Chưa chọn đủ ca và đối tượng gán.')
        return redirect('cham_cong:schedule')
    target = form.cleaned_data['target_type']
    assignment = ShiftAssignment(shift=form.cleaned_data['shift'], is_active=True)
    if target == AssignmentForm.TARGET_USER:
        assignment.user = form.cleaned_data['user']
        ShiftAssignment.objects.filter(user=assignment.user, is_active=True).update(is_active=False)
    elif target == AssignmentForm.TARGET_DIVISION:
        assignment.division = form.cleaned_data['division']
        ShiftAssignment.objects.filter(
            division=assignment.division, user__isnull=True, is_active=True,
        ).update(is_active=False)
    else:
        assignment.department = form.cleaned_data['department']
        ShiftAssignment.objects.filter(
            department=assignment.department,
            division__isnull=True,
            user__isnull=True,
            is_active=True,
        ).update(is_active=False)
    assignment.save()
    write_log(request.user, 'assignment_save', f'Gán ca {assignment.shift.name} cho {assignment.target_label}')
    messages.success(request, 'Đã gán ca. Mỗi người chỉ dùng một ca, ưu tiên gán riêng từng nhân viên.')
    return redirect('cham_cong:schedule')


@login_required
@require_POST
def assignment_off(request, pk):
    denied = _config_required(request)
    if denied:
        return denied
    assignment = get_object_or_404(ShiftAssignment, pk=pk, is_active=True)
    assignment.is_active = False
    assignment.save(update_fields=['is_active'])
    write_log(request.user, 'assignment_off', f'Gỡ ca {assignment.shift.name} khỏi {assignment.target_label}')
    messages.success(request, 'Đã gỡ gán ca.')
    return redirect('cham_cong:schedule')


@login_required
@require_POST
def policy_save(request):
    denied = _config_required(request)
    if denied:
        return denied
    form = PolicyForm(request.POST, instance=AttendancePolicy.load())
    if form.is_valid():
        form.save()
        write_log(request.user, 'policy_save', 'Cập nhật thiết lập chấm công')
        messages.success(request, 'Đã lưu thiết lập.')
    else:
        messages.error(request, 'Thiết lập chưa hợp lệ.')
    return redirect('cham_cong:hr_config')


@login_required
@require_POST
def holiday_save(request):
    denied = _config_required(request)
    if denied:
        return denied
    form = HolidayForm(request.POST)
    if form.is_valid():
        holiday = form.save()
        write_log(request.user, 'holiday_save', f'Thêm ngày lễ {holiday.name}')
        messages.success(request, 'Đã thêm ngày lễ.')
    else:
        messages.error(request, 'Ngày lễ bị trùng hoặc chưa đủ thông tin.')
    return redirect('cham_cong:schedule')


@login_required
@require_POST
def holiday_delete(request, pk):
    denied = _config_required(request)
    if denied:
        return denied
    holiday = get_object_or_404(Holiday, pk=pk)
    label = str(holiday)
    holiday.delete()
    write_log(request.user, 'holiday_delete', f'Xóa ngày lễ {label}')
    messages.success(request, 'Đã xóa ngày lễ.')
    return redirect('cham_cong:schedule')


@login_required
def site_list(request):
    denied = _config_required(request)
    if denied:
        return denied
    return render(request, 'cham_cong/site_list.html', {
        'sites': WorkSite.objects.prefetch_related('ips'),
    })


@login_required
def site_edit(request, pk=None):
    denied = _config_required(request)
    if denied:
        return denied
    site = get_object_or_404(WorkSite, pk=pk) if pk else WorkSite()
    if request.method == 'POST':
        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            saved = form.save()
            saved.ips.all().delete()
            WorkSiteIp.objects.bulk_create([
                WorkSiteIp(site=saved, cidr=cidr) for cidr in form.cleaned_data['ip_text']
            ])
            write_log(request.user, 'site_save', f'Lưu địa điểm {saved.name}')
            messages.success(request, 'Đã lưu địa điểm chấm công.')
            return redirect('cham_cong:sites')
    else:
        form = SiteForm(instance=site)
    return render(request, 'cham_cong/site_form.html', {'form': form, 'site': site})


def _report_month(request):
    month_text = (request.GET.get('month') or timezone.localdate().strftime('%Y-%m')).strip()
    try:
        year, month = (int(part) for part in month_text.split('-', 1))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        today = timezone.localdate()
        year, month = today.year, today.month
        month_text = f'{year:04d}-{month:02d}'
    return year, month, month_text


@login_required
def hr_config(request):
    denied = _config_required(request)
    if denied:
        return denied
    year, month, month_text = _report_month(request)
    return render(request, 'cham_cong/hr_config.html', {
        'month': month_text,
        'report': monthly_attendance_report(year, month),
        'fund': payroll_fund(year, month),
        'policy_form': PolicyForm(instance=AttendancePolicy.load()),
        'policy': AttendancePolicy.load(),
        'sites': WorkSite.objects.prefetch_related('ips'),
        'logs': AttendanceLog.objects.select_related('actor', 'actor__profile')[:8],
    })


@login_required
def hr_report(request):
    denied = _config_required(request)
    if denied:
        return denied
    year, month, month_text = _report_month(request)
    view = request.GET.get('view') or 'late'
    if view not in ('late', 'absent', 'ot', 'fund'):
        view = 'late'
    report = monthly_attendance_report(year, month)
    people = report['people']
    if view == 'late':
        rows = [person for person in people if person['late'] or person['early']]
    elif view == 'absent':
        rows = [person for person in people if person['absent']]
    elif view == 'ot':
        rows = [person for person in people if person['ot_minutes']]
    else:
        rows = []
    return render(request, 'cham_cong/hr_report.html', {
        'month': month_text,
        'view': view,
        'report': report,
        'rows': rows,
        'fund': fund_report(year, month),
    })


_LOG_LABELS = {
    'clock_in': 'Chấm vào',
    'clock_out': 'Chấm ra',
    'break_out': 'Ra nghỉ',
    'break_in': 'Vào lại',
    'supplement_submit': 'Gửi bổ sung',
    'supplement_approve': 'Duyệt bổ sung',
    'supplement_reject': 'Từ chối bổ sung',
    'adjustment_submit': 'Xin chỉnh công',
    'adjustment_approve': 'Duyệt chỉnh công',
    'adjustment_reject': 'Từ chối chỉnh công',
    'timesheet_lock': 'Khóa bảng công',
    'timesheet_unlock': 'Mở bảng công',
    'leave_submit': 'Gửi đơn nghỉ',
    'leave_approve': 'Duyệt đơn nghỉ',
    'leave_reject': 'Từ chối đơn nghỉ',
    'leave_cancel': 'Hủy đơn nghỉ',
    'payroll_calculate': 'Tính lương',
    'payroll_close': 'Chốt lương',
    'payroll_reopen': 'Mở kỳ lương',
    'salary_save': 'Lưu mức lương',
    'pay_adjustment_submit': 'Gửi thưởng/phạt',
    'pay_adjustment_approve': 'Duyệt thưởng/phạt',
    'pay_adjustment_reject': 'Từ chối thưởng/phạt',
    'shift_save': 'Lưu ca',
    'assignment_save': 'Gán ca',
    'assignment_off': 'Gỡ ca',
    'holiday_save': 'Thêm ngày lễ',
    'holiday_delete': 'Xóa ngày lễ',
    'policy_save': 'Lưu quy tắc',
    'site_save': 'Lưu địa điểm',
}


@login_required
def hr_log(request):
    denied = _config_required(request)
    if denied:
        return denied
    action = (request.GET.get('action') or '').strip()
    query = (request.GET.get('q') or '').strip()
    logs = AttendanceLog.objects.select_related('actor', 'actor__profile', 'target_user', 'target_user__profile')
    if action:
        logs = logs.filter(action=action)
    if query:
        logs = logs.filter(message__icontains=query)
    page = Paginator(logs, 50).get_page(request.GET.get('page'))
    for row in page.object_list:
        row.action_label = _LOG_LABELS.get(row.action, row.action)
    return render(request, 'cham_cong/hr_log.html', {
        'page': page,
        'action': action,
        'query': query,
        'actions': _LOG_LABELS,
    })
