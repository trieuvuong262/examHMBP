"""View cổng đối tác GC: đăng nhập, danh sách đơn, nhận đơn, báo SL ngày × size, thống kê."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from san_xuat.hub_models import SxSubcontractOrder
from san_xuat.partner_models import GcOutputReport
from san_xuat.partner_portal import auth
from san_xuat.services.gc_output import (
    OPEN_STATUSES,
    GcOutputError,
    accept_order,
    cancel_report,
    partner_orders,
    reported_totals,
    submit_report,
)

ZERO = Decimal('0')


def _ctx(request, **extra):
    acc = request.gc_account
    return {
        'gc_account': acc,
        'gc_partner': acc.partner if acc else None,
        'is_owner': bool(acc and acc.role == acc.ROLE_OWNER),
        **extra,
    }


def login_view(request):
    if request.gc_account:
        return redirect('home')
    error = ''
    username = ''
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        try:
            acc = auth.authenticate(username, request.POST.get('password') or '')
        except auth.PartnerLoginError as exc:
            error = str(exc)
        else:
            auth.login(request, acc)
            nxt = request.POST.get('next') or ''
            if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
                return redirect(nxt)
            return redirect('home')
    return render(request, 'partner_portal/login.html', {
        'error': error,
        'username': username,
        'next': request.GET.get('next') or request.POST.get('next') or '',
    })


@require_POST
def logout_view(request):
    auth.logout(request)
    return redirect('login')


@auth.partner_login_required
def change_password(request):
    acc = request.gc_account
    errors = []
    if request.method == 'POST':
        old = request.POST.get('old_password') or ''
        new1 = request.POST.get('new_password1') or ''
        new2 = request.POST.get('new_password2') or ''
        if not acc.check_password(old):
            errors.append('Mật khẩu hiện tại không đúng.')
        elif new1 != new2:
            errors.append('Hai lần nhập mật khẩu mới không khớp.')
        elif new1 == old:
            errors.append('Mật khẩu mới phải khác mật khẩu cũ.')
        else:
            try:
                validate_password(new1)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if not errors:
            acc.set_password(new1)
            acc.must_change_password = False
            acc.save(update_fields=['password', 'must_change_password'])
            auth.refresh_session_hash(request, acc)
            messages.success(request, 'Đã đổi mật khẩu.')
            return redirect('home')
    return render(request, 'partner_portal/change_password.html', _ctx(request, errors=errors))


def _order_row(order) -> dict:
    tot = reported_totals(order)
    return {
        'order': order,
        'approved': tot['approved'],
        'pending': tot['pending'],
        'remain': max(order.qty - tot['reported'], ZERO),
        'pct': (tot['approved'] * 100 / order.qty).quantize(Decimal('0.1')) if order.qty else ZERO,
        'is_open': order.status in OPEN_STATUSES,
        'is_late': bool(order.due_date and order.status in OPEN_STATUSES and order.due_date < timezone.localdate()),
    }


@auth.partner_login_required
def home(request):
    acc = request.gc_account
    tab = (request.GET.get('tab') or 'open').strip()
    qs = partner_orders(acc.partner).prefetch_related('output_reports')
    if tab == 'open':
        qs = qs.filter(status__in=OPEN_STATUSES)
    elif tab == 'done':
        qs = qs.filter(status__in=[SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE])
    rows = [_order_row(o) for o in qs.order_by('due_date', '-order_date', '-pk')[:200]]
    all_orders = partner_orders(acc.partner)
    new_count = all_orders.filter(
        status__in=OPEN_STATUSES, partner_accepted_at__isnull=True,
    ).count()
    summary = {
        'total': all_orders.count(),
        'open': all_orders.filter(status__in=OPEN_STATUSES).count(),
        'done': all_orders.filter(status__in=[SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE]).count(),
        'late': all_orders.filter(status__in=OPEN_STATUSES, due_date__lt=timezone.localdate()).count(),
    }
    return render(request, 'partner_portal/home.html', _ctx(
        request, rows=rows, tab=tab, new_count=new_count, summary=summary,
    ))


def _size_rows(order) -> list[dict]:
    """Size của tổ thuê trên LSX: kế hoạch / đã làm / còn lại. Không có LSX → 1 dòng 'Tổng'."""
    from san_xuat.services.subcontract_progress import team_size_status

    status = team_size_status(order)
    if not status:
        return [{'size': 'Tổng', 'plan': order.qty, 'done': ZERO, 'remain': order.qty}]
    return [
        {'size': size, 'plan': row['plan'], 'done': row['done'], 'remain': row['remain']}
        for size, row in status.items()
    ]


@auth.partner_login_required
def order_detail(request, pk: int):
    acc = request.gc_account
    order = get_object_or_404(partner_orders(acc.partner), pk=pk)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'accept':
                accept_order(order=order, account=acc)
                messages.success(request, f'Đã nhận đơn {order.code}.')
            elif action == 'report':
                sizes = {
                    key[5:]: (request.POST.get(key) or '').strip()
                    for key in request.POST if key.startswith('size_')
                }
                sizes = {k: v for k, v in sizes.items() if v}
                submit_report(
                    order_id=order.pk,
                    account=acc,
                    work_date=parse_date((request.POST.get('work_date') or '').strip()),
                    size_qtys=sizes,
                    note=request.POST.get('note') or '',
                )
                messages.success(request, 'Đã gửi báo sản lượng — chờ JustPlay QC duyệt.')
            elif action == 'cancel_report':
                cancel_report(report_id=int(request.POST.get('report_id') or 0), account=acc)
                messages.success(request, 'Đã huỷ báo cáo.')
        except GcOutputError as exc:
            messages.error(request, str(exc))
        except GcOutputReport.DoesNotExist:
            messages.error(request, 'Không tìm thấy báo cáo.')
        return redirect('order_detail', pk=order.pk)

    reports = order.output_reports.select_related('account').order_by('-work_date', '-pk')
    return render(request, 'partner_portal/order_detail.html', _ctx(
        request,
        row=_order_row(order),
        order=order,
        size_rows=_size_rows(order),
        reports=reports,
        today=timezone.localdate(),
        show_price=acc.role == acc.ROLE_OWNER,
    ))


@auth.owner_required
def reports(request):
    """Thống kê đối tác (chủ ĐT): SL duyệt, tỉ lệ đạt, đúng hạn, thành tiền theo tháng."""
    from san_xuat.services.gc_kpi import partner_kpi

    acc = request.gc_account
    month = (request.GET.get('month') or timezone.localdate().strftime('%Y-%m')).strip()
    kpi = partner_kpi(acc.partner, month=month)
    return render(request, 'partner_portal/reports.html', _ctx(request, kpi=kpi, month=kpi['month_value']))
