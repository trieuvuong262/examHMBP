"""View cổng đối tác GC: đăng nhập, danh sách đơn, nhận/từ chối đơn, báo SL ngày × size, giá, KPI.

Vai trò: Chủ / quản lý (``ROLE_OWNER``) nhận/từ chối đơn, xem giá, thành tiền, KPI.
Nhân viên (``ROLE_STAFF``) chỉ báo sản lượng cho đơn đã nhận.
"""

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
from san_xuat.partner_models import GcOutputReport, GcPartnerAccount, GcPartnerActivity as Act
from san_xuat.partner_portal import activity, auth
from san_xuat.services.gc_output import (
    OPEN_STATUSES,
    GcOutputError,
    accept_order,
    cancel_report,
    partner_orders,
    reject_order,
    reported_totals,
    submit_report,
)

ZERO = Decimal('0')
DONE_STATUSES = (SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE)


def _ctx(request, **extra):
    acc = request.gc_account
    return {
        'gc_account': acc,
        'gc_partner': acc.partner if acc else None,
        'is_owner': auth.is_owner(acc),
        **extra,
    }


def login_view(request):
    if request.gc_account:
        return redirect('home')
    error = ''
    username = ''
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        if activity.ip_blocked(request):
            error = auth.GENERIC_LOGIN_ERROR
            activity.log(request, Act.ACTION_LOGIN_FAILED, username=username, detail='Chặn theo IP')
        else:
            try:
                acc = auth.authenticate(username, request.POST.get('password') or '')
            except auth.PartnerLoginError as exc:
                error = str(exc)
                activity.record_ip_failure(request)
                failed = GcPartnerAccount.objects.filter(username=username.lower()).first()
                activity.log(request, Act.ACTION_LOGIN_FAILED, account=failed, username=username)
            else:
                auth.login(request, acc)
                activity.clear_ip_failures(request)
                activity.log(request, Act.ACTION_LOGIN, account=acc)
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
    if request.gc_account:
        activity.log(request, Act.ACTION_LOGOUT)
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
            activity.log(request, Act.ACTION_PASSWORD)
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
        'over': max(tot['approved'] - order.qty, ZERO),
        'pct': (tot['approved'] * 100 / order.qty).quantize(Decimal('0.1')) if order.qty else ZERO,
        'is_open': order.status in OPEN_STATUSES,
        'is_new': order.status in OPEN_STATUSES and not order.partner_accepted_at,
        'is_late': bool(order.due_date and order.status in OPEN_STATUSES and order.due_date < timezone.localdate()),
        'amount': (tot['approved'] * (order.unit_price or ZERO)).quantize(Decimal('1')),
    }


@auth.partner_login_required
def home(request):
    acc = request.gc_account
    tab = (request.GET.get('tab') or 'open').strip()
    qs = partner_orders(acc.partner).prefetch_related('output_reports')
    if tab == 'new':
        qs = qs.filter(status__in=OPEN_STATUSES, partner_accepted_at__isnull=True)
    elif tab == 'open':
        qs = qs.filter(status__in=OPEN_STATUSES)
    elif tab == 'done':
        qs = qs.filter(status__in=DONE_STATUSES)
    rows = [_order_row(o) for o in qs.order_by('due_date', '-order_date', '-pk')[:200]]
    all_orders = partner_orders(acc.partner)
    summary = {
        'new': all_orders.filter(status__in=OPEN_STATUSES, partner_accepted_at__isnull=True).count(),
        'open': all_orders.filter(status__in=OPEN_STATUSES).count(),
        'done': all_orders.filter(status__in=DONE_STATUSES).count(),
        'late': all_orders.filter(status__in=OPEN_STATUSES, due_date__lt=timezone.localdate()).count(),
        'pending_reports': GcOutputReport.objects.filter(
            partner=acc.partner, status=GcOutputReport.STATUS_SUBMITTED,
        ).count(),
    }
    return render(request, 'partner_portal/home.html', _ctx(
        request, rows=rows, tab=tab, new_count=summary['new'], summary=summary,
    ))


def _size_rows(order) -> list[dict]:
    """Size của tổ thuê trên LSX: kế hoạch / đã làm / còn lại. Không đọc được → 1 dòng 'Tổng'."""
    from san_xuat.services.subcontract_progress import team_size_status

    status = team_size_status(order)
    if not status:
        return [{'size': 'Tổng', 'plan': order.qty, 'done': ZERO, 'remain': order.qty}]
    return [
        {'size': size, 'plan': row['plan'], 'done': row['done'], 'remain': row['remain']}
        for size, row in status.items()
    ]


def _handle_order_post(request, order, size_rows) -> None:
    acc = request.gc_account
    action = (request.POST.get('action') or '').strip()
    if action in {'accept', 'reject'} and not auth.is_owner(acc):
        raise GcOutputError('Chỉ tài khoản chủ / quản lý đối tác được nhận hoặc từ chối đơn.')
    if action == 'accept':
        accept_order(order=order, account=acc)
        activity.log(request, Act.ACTION_ACCEPT, order=order, detail=order.code)
        messages.success(request, f'Đã nhận đơn {order.code}.')
    elif action == 'reject':
        reason = request.POST.get('reason') or ''
        reject_order(order=order, account=acc, reason=reason)
        activity.log(request, Act.ACTION_REJECT, order=order, detail=f'{order.code}: {reason}')
        messages.success(request, f'Đã từ chối đơn {order.code}. JustPlay sẽ sắp xếp lại.')
    elif action == 'report':
        allowed = {row['size'] for row in size_rows}
        sizes = {
            key[5:]: (request.POST.get(key) or '').strip()
            for key in request.POST if key.startswith('size_')
        }
        sizes = {k: v for k, v in sizes.items() if v and k in allowed}
        report = submit_report(
            order_id=order.pk,
            account=acc,
            work_date=parse_date((request.POST.get('work_date') or '').strip()),
            size_qtys=sizes,
            note=request.POST.get('note') or '',
        )
        activity.log(
            request, Act.ACTION_REPORT, order=order,
            detail=f'{order.code} {report.work_date:%d/%m/%Y}: {report.total_qty:,.0f}',
        )
        messages.success(request, 'Đã gửi báo sản lượng — chờ JustPlay QC duyệt.')
    elif action == 'cancel_report':
        report = cancel_report(report_id=int(request.POST.get('report_id') or 0), account=acc)
        activity.log(
            request, Act.ACTION_CANCEL_REPORT, order=order,
            detail=f'{order.code} {report.work_date:%d/%m/%Y}: {report.total_qty:,.0f}',
        )
        messages.success(request, 'Đã huỷ báo cáo.')


@auth.partner_login_required
def order_detail(request, pk: int):
    acc = request.gc_account
    order = get_object_or_404(partner_orders(acc.partner), pk=pk)
    size_rows = _size_rows(order)
    if request.method == 'POST':
        try:
            _handle_order_post(request, order, size_rows)
        except GcOutputError as exc:
            messages.error(request, str(exc))
        except GcOutputReport.DoesNotExist:
            messages.error(request, 'Không tìm thấy báo cáo.')
        if not partner_orders(acc.partner).filter(pk=order.pk).exists():
            return redirect('home')
        return redirect('order_detail', pk=order.pk)

    reports = order.output_reports.select_related('account', 'cancelled_by').order_by('-work_date', '-pk')
    return render(request, 'partner_portal/order_detail.html', _ctx(
        request,
        row=_order_row(order),
        order=order,
        size_rows=size_rows,
        reports=reports,
        today=timezone.localdate(),
        show_price=auth.is_owner(acc),
    ))


@auth.owner_required
def price_list(request):
    """Đơn giá GC đang áp dụng của đối tác (đã duyệt, còn hiệu lực)."""
    from django.db.models import Q

    from san_xuat.partner_models import GcPriceRule

    acc = request.gc_account
    today = timezone.localdate()
    rules = (
        GcPriceRule.objects.filter(
            partner=acc.partner, status=GcPriceRule.STATUS_APPROVED, valid_from__lte=today,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        .order_by('team_slug', 'product_code', '-valid_from')
    )
    return render(request, 'partner_portal/price_list.html', _ctx(request, rules=rules, today=today))


@auth.owner_required
def reports(request):
    """KPI đối tác (chủ ĐT): điểm, hạng, 4 chỉ tiêu, SL duyệt, thành tiền theo tháng."""
    from san_xuat.services.gc_kpi import current_month, kpi_for_display

    acc = request.gc_account
    month = (request.GET.get('month') or current_month()).strip()
    kpi = kpi_for_display(acc.partner, month=month)
    return render(request, 'partner_portal/reports.html', _ctx(request, kpi=kpi, month=kpi['month_value']))


def page_not_found(request, exception=None):
    """404 riêng cho pn — template 404 nội bộ dùng URL không có trong urlconf pn (→ lỗi 500)."""
    acc = getattr(request, 'gc_account', None)
    return render(request, 'partner_portal/404.html', {
        'gc_account': acc,
        'gc_partner': acc.partner if acc else None,
        'is_owner': auth.is_owner(acc),
    }, status=404)


def server_error(request):
    from django.http import HttpResponseServerError

    return HttpResponseServerError(
        '<!doctype html><meta charset="utf-8"><title>Lỗi</title>'
        '<p style="font-family:sans-serif;padding:2rem">Có lỗi xảy ra. Vui lòng thử lại hoặc liên hệ JustPlay.'
        ' <a href="/">Về trang chủ</a></p>'
    )
