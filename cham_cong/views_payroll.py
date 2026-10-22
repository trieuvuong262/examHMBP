from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cham_cong.forms import PayAdjustmentForm, SalaryProfileForm
from cham_cong.models import PayAdjustment, PayrollPeriod, SalaryProfile
from cham_cong.payrollbook import compute_month, is_closed, save_calculation, stored_rows, period_for
from cham_cong.permissions import (
    can_approve_pay_adjustment,
    can_configure,
    can_punch,
    can_view_company,
    can_view_payslip,
)
from cham_cong.services import team_user_ids, write_log
from cham_cong.timesheet import parse_month
from cham_cong.views import _deny_punch


def _scope_ids(user):
    if can_view_company(user):
        return None
    return [user.pk, *team_user_ids(user)]


def _scope_users(user):
    base = User.objects.filter(is_active=True, profile__is_employed=True).select_related(
        'profile', 'profile__department',
    )
    ids = _scope_ids(user)
    if ids is None:
        return base.order_by('profile__full_name', 'username')
    return base.filter(Q(pk__in=ids)).order_by('profile__full_name', 'username')


def _rows_for(user, year, month):
    period = period_for(year, month)
    ids = _scope_ids(user)
    if period and period.status == PayrollPeriod.STATUS_CLOSED:
        allowed = ids if ids is not None else list(
            period.slips.values_list('user_id', flat=True)
        )
        return period, stored_rows(period, allowed), True
    if ids is None:
        return period, compute_month(year, month), False
    return period, compute_month(year, month, ids), False


@login_required
def payroll(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    today = timezone.localdate()
    year, month, month_text = parse_month(request.GET.get('month'), today)
    period, rows, closed = _rows_for(request.user, year, month)
    adjustments = PayAdjustment.objects.filter(year=year, month=month).select_related(
        'user', 'user__profile', 'created_by',
    )
    ids = _scope_ids(request.user)
    if ids is not None:
        adjustments = adjustments.filter(user_id__in=ids)
    adjustments = list(adjustments[:200])
    for item in adjustments:
        item.can_decide = item.status == PayAdjustment.STATUS_PENDING and can_approve_pay_adjustment(
            request.user, item,
        )
    return render(request, 'cham_cong/payroll.html', {
        'month': month_text,
        'year': year,
        'focus_month': month,
        'period': period,
        'closed': closed,
        'rows': rows,
        'shown_fund': sum((row['net_pay'] for row in rows), Decimal('0')),
        'adjustments': adjustments,
        'can_manage': can_configure(request.user),
        'can_add_adjustment': can_configure(request.user) or bool(team_user_ids(request.user)),
    })


@login_required
def payroll_slip(request, user_id):
    if not can_punch(request.user):
        return _deny_punch(request)
    employee = get_object_or_404(User, pk=user_id)
    if not can_view_payslip(request.user, employee):
        messages.error(request, 'Bạn không xem được phiếu lương này.')
        return redirect('cham_cong:payroll')
    today = timezone.localdate()
    year, month, month_text = parse_month(request.GET.get('month'), today)
    period, rows, closed = _rows_for(request.user, year, month)
    row = next((item for item in rows if item['user'].pk == employee.pk), None)
    return render(request, 'cham_cong/payroll_slip.html', {
        'month': month_text,
        'row': row,
        'employee': employee,
        'closed': closed,
        'period': period,
    })


@login_required
@require_POST
def payroll_calculate(request):
    if not can_configure(request.user):
        messages.error(request, 'Chỉ nhân sự tính kỳ lương.')
        return redirect('cham_cong:payroll')
    today = timezone.localdate()
    year, month, text = parse_month(request.POST.get('month'), today)
    period, error = save_calculation(year, month, request.user)
    if error:
        messages.error(request, error)
    else:
        write_log(request.user, 'payroll_calculate', f'Tính lương {month:02d}/{year}')
        messages.success(request, f'Đã tính lương tháng {month:02d}/{year}.')
    return redirect(f"{reverse('cham_cong:payroll')}?month={text}")


@login_required
@require_POST
def payroll_close(request):
    if not can_configure(request.user):
        messages.error(request, 'Chỉ nhân sự chốt kỳ lương.')
        return redirect('cham_cong:payroll')
    today = timezone.localdate()
    year, month, text = parse_month(request.POST.get('month'), today)
    action = request.POST.get('action')
    period = period_for(year, month)
    if action == 'reopen':
        if not period or period.status != PayrollPeriod.STATUS_CLOSED:
            messages.error(request, 'Kỳ này chưa chốt.')
            return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
        period.status = PayrollPeriod.STATUS_DRAFT
        period.closed_by = None
        period.closed_at = None
        period.save()
        write_log(request.user, 'payroll_reopen', f'Mở lại kỳ lương {month:02d}/{year}')
        messages.success(request, f'Đã mở lại kỳ lương {month:02d}/{year}.')
        return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    period, error = save_calculation(year, month, request.user)
    if error:
        messages.error(request, error)
        return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    period.status = PayrollPeriod.STATUS_CLOSED
    period.closed_by = request.user
    period.closed_at = timezone.now()
    period.save()
    write_log(request.user, 'payroll_close', f'Chốt lương {month:02d}/{year}')
    messages.success(request, f'Đã chốt lương tháng {month:02d}/{year}.')
    return redirect(f"{reverse('cham_cong:payroll')}?month={text}")


@login_required
def salary_list(request):
    if not can_configure(request.user):
        messages.error(request, 'Chỉ nhân sự nhập mức lương.')
        return redirect('cham_cong:payroll')
    users = list(_scope_users(request.user))
    saved = {
        item.user_id: item
        for item in SalaryProfile.objects.filter(user__in=users)
    }
    rows = []
    for user in users:
        item = saved.get(user.pk)
        rows.append({
            'user': user,
            'name': user.profile.full_name or user.username,
            'department': user.profile.department.name if user.profile.department_id else '',
            'base_salary': item.base_salary if item else 0,
            'meal_allowance': item.meal_allowance if item else 0,
            'transport_allowance': item.transport_allowance if item else 0,
            'phone_allowance': item.phone_allowance if item else 0,
        })
    return render(request, 'cham_cong/salary_list.html', {'rows': rows})


@login_required
def salary_edit(request, user_id):
    if not can_configure(request.user):
        messages.error(request, 'Chỉ nhân sự nhập mức lương.')
        return redirect('cham_cong:payroll')
    employee = get_object_or_404(
        User.objects.select_related('profile'), pk=user_id, is_active=True, profile__is_employed=True,
    )
    salary, _created = SalaryProfile.objects.get_or_create(user=employee)
    if request.method == 'POST':
        form = SalaryProfileForm(request.POST, instance=salary)
        if form.is_valid():
            form.save()
            write_log(request.user, 'salary_save', f'Lưu mức lương của {employee.profile.full_name or employee.username}', employee)
            messages.success(request, 'Đã lưu mức lương.')
            return redirect('cham_cong:salary_list')
    else:
        form = SalaryProfileForm(instance=salary)
    return render(request, 'cham_cong/salary_form.html', {'form': form, 'employee': employee})


@login_required
def pay_adjustment_create(request):
    if not can_punch(request.user):
        return _deny_punch(request)
    if not (can_configure(request.user) or team_user_ids(request.user)):
        messages.error(request, 'Bạn không nhập thưởng hoặc phạt.')
        return redirect('cham_cong:payroll')
    today = timezone.localdate()
    year, month, text = parse_month(request.GET.get('month') or request.POST.get('month'), today)
    if is_closed(year, month):
        messages.error(request, 'Kỳ lương đã chốt.')
        return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    users = _scope_users(request.user).exclude(pk=request.user.pk)
    if request.method == 'POST':
        form = PayAdjustmentForm(request.POST, users=users)
        if form.is_valid():
            item = form.save(commit=False)
            item.year = year
            item.month = month
            item.created_by = request.user
            item.save()
            write_log(
                request.user, 'pay_adjustment_submit',
                f'Gửi {item.get_kind_display()} {month:02d}/{year}', item.user,
            )
            messages.success(request, 'Đã gửi. Cần được duyệt trước khi vào phiếu lương.')
            return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    else:
        form = PayAdjustmentForm(users=users)
    return render(request, 'cham_cong/pay_adjustment_form.html', {
        'form': form,
        'month': text,
    })


@login_required
@require_POST
def pay_adjustment_decide(request, pk):
    item = get_object_or_404(PayAdjustment.objects.select_related('user'), pk=pk)
    text = f'{item.year:04d}-{item.month:02d}'
    if item.status != PayAdjustment.STATUS_PENDING or not can_approve_pay_adjustment(request.user, item):
        messages.error(request, 'Bạn không duyệt khoản này.')
        return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    if is_closed(item.year, item.month) and request.POST.get('decision') == 'approve':
        messages.error(request, 'Kỳ lương đã chốt.')
        return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    note = (request.POST.get('note') or '').strip()
    decision = request.POST.get('decision')
    if decision == 'reject':
        if not note:
            messages.error(request, 'Nhập lý do từ chối.')
            return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
        item.status = PayAdjustment.STATUS_REJECTED
    elif decision == 'approve':
        item.status = PayAdjustment.STATUS_APPROVED
    else:
        messages.error(request, 'Thao tác duyệt không hợp lệ.')
        return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
    item.decision_note = note
    item.decided_by = request.user
    item.decided_at = timezone.now()
    item.save()
    write_log(
        request.user,
        'pay_adjustment_approve' if item.status == PayAdjustment.STATUS_APPROVED else 'pay_adjustment_reject',
        f'{item.get_status_display()} {item.get_kind_display()} {item.month:02d}/{item.year}',
        item.user,
    )
    messages.success(request, 'Đã cập nhật thưởng/phạt. Hãy tính lại kỳ lương nếu kỳ chưa chốt.')
    return redirect(f"{reverse('cham_cong:payroll')}?month={text}")
