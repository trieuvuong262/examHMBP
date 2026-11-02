"""Menu Gia Công — phiếu thuê GC, tổ gia công, tài khoản đối tác, thống kê.

Mọi màn dùng menu quyền ``subcontract``; người có quyền KHSX (plan / plan_board)
vẫn vào được qua alias trong ``MENU_PATH_ACCESS_ALIASES``.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from hrm.menu_permissions import (
    handle_menu_access_denied,
    user_can_create_menu,
    user_can_delete_menu,
    user_can_export_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.hub_models import SxSubcontractOrder
from san_xuat.list_filters import (
    SUBCONTRACT_WORK_STATUS_CHOICES,
    SUBCONTRACT_WORK_STATUS_DONE,
    SUBCONTRACT_WORK_STATUS_RUNNING,
    parse_sx_date,
)
from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context
from san_xuat.partner_models import GcPartner, GcPartnerAccount
from san_xuat.views_gc_partner import MENU, _can_edit, _can_view

_OPEN_STATUSES = (SxSubcontractOrder.STATUS_DRAFT, SxSubcontractOrder.STATUS_SENT)


def _any_menu(check, user, *menus: str) -> bool:
    return any(check(user, MODULE_SAN_XUAT, key) for key in menus)


def _can_delete_order(user) -> bool:
    """Xóa / hủy phiếu GC — giữ quyền cũ của KHSX (Chuyển SX) + quyền Gia công."""
    return (
        _any_menu(user_can_create_menu, user, MENU, 'plan_board')
        or _any_menu(user_can_update_menu, user, MENU, 'plan_board', 'plan')
        or user_can_delete_menu(user, MODULE_SAN_XUAT, MENU)
    )


def _can_export(user) -> bool:
    return _any_menu(user_can_export_menu, user, MENU, 'plan_board')


def _denied(request):
    return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU)


# ---------------------------------------------------------------------------
# Phiếu thuê gia công
# ---------------------------------------------------------------------------

def _delete_order(request, raw_id: str) -> None:
    from san_xuat.services.phase3 import (
        Phase3Error,
        advance_subcontract_order,
        delete_subcontract_order,
    )

    if not _can_delete_order(request.user):
        messages.error(request, 'Bạn không có quyền xóa phiếu thuê gia công.')
        return
    raw_id = (raw_id or '').strip()
    gc = (
        SxSubcontractOrder.objects.filter(pk=int(raw_id), is_demo=False).first()
        if raw_id.isdigit() else None
    )
    if gc is None:
        messages.error(request, 'Không tìm thấy phiếu gia công.')
        return
    code = gc.code
    try:
        if gc.status == SxSubcontractOrder.STATUS_DRAFT:
            delete_subcontract_order(order_id=gc.pk)
            messages.success(request, f'Đã xóa phiếu {code}. Công đoạn trên KHSX trở lại Thuê GC.')
        elif gc.status in (SxSubcontractOrder.STATUS_DONE, SxSubcontractOrder.STATUS_CANCELLED):
            messages.error(request, f'Không xóa được phiếu {code} ({gc.get_status_display()}).')
        else:
            advance_subcontract_order(order_id=gc.pk, to_status=SxSubcontractOrder.STATUS_CANCELLED)
            messages.success(request, f'Đã hủy phiếu {code}. Công đoạn trên KHSX trở lại Thuê GC.')
    except Phase3Error as exc:
        messages.error(request, str(exc))


@login_required
def subcontract_list(request):
    """Danh sách phiếu thuê gia công (trước đây là tab ẩn trên bảng KHSX)."""
    from san_xuat.services.team_division_map import team_slug_choices

    if not _can_view(request.user):
        return _denied(request)

    if request.method == 'POST':
        if (request.POST.get('action') or '').strip() == 'delete_gc':
            _delete_order(request, request.POST.get('gc_id') or '')
        return redirect(request.get_full_path())

    gc_open = (request.GET.get('gc') or '').strip()
    if gc_open.isdigit():
        return redirect('san_xuat:subcontract_detail', pk=int(gc_open))

    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or request.GET.get('gc_status') or '').strip()
    team = (request.GET.get('team') or request.GET.get('gc_team') or '').strip().lower()
    partner_raw = (request.GET.get('partner') or '').strip()
    date_from = parse_sx_date(request.GET.get('date_from') or '')
    date_to = parse_sx_date(request.GET.get('date_to') or '')
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    qs = (
        SxSubcontractOrder.objects.filter(is_demo=False)
        .select_related('sales_order', 'production_order', 'partner')
        .order_by('-order_date', '-pk')
    )
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(vendor_name__icontains=q)
            | Q(product_code__icontains=q)
            | Q(product_name__icontains=q)
            | Q(sales_order__code__icontains=q)
            | Q(production_order__code__icontains=q)
        )
    if date_from:
        qs = qs.filter(order_date__gte=date_from)
    if date_to:
        qs = qs.filter(order_date__lte=date_to)
    if status == SUBCONTRACT_WORK_STATUS_RUNNING:
        qs = qs.filter(status__in=_OPEN_STATUSES)
    elif status == SUBCONTRACT_WORK_STATUS_DONE:
        qs = qs.filter(status__in=[SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE])
    elif status == SxSubcontractOrder.STATUS_CANCELLED:
        qs = qs.filter(status=SxSubcontractOrder.STATUS_CANCELLED)
    else:
        qs = qs.exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
    if team:
        qs = qs.filter(team_slug=team)
    if partner_raw.isdigit():
        qs = qs.filter(partner_id=int(partner_raw))
    if (request.GET.get('sort') or '').strip():
        qs = apply_sx_list_sort(qs, request, 'subcontract')

    has_filters = bool(q or status or team or partner_raw or date_from or date_to)
    from utilities.date_range_filter import date_range_span_context

    return render(request, 'san_xuat/subcontract_list.html', {
        **sx_list_grid_context(request, 'subcontract'),
        **date_range_span_context(date_from, date_to),
        'range_all': not (date_from or date_to),
        'items': list(qs.select_related('created_by')[:500]),
        'search_query': q,
        'status_filter': status,
        'team_filter': team,
        'partner_filter': partner_raw,
        'filter_date_from': date_from,
        'filter_date_to': date_to,
        'has_filters': has_filters,
        'status_choices': SUBCONTRACT_WORK_STATUS_CHOICES,
        'team_choices': team_slug_choices(),
        'partners': GcPartner.objects.order_by('-is_active', 'name'),
        'can_delete_gc': _can_delete_order(request.user),
        'can_export': _can_export(request.user),
    })


# ---------------------------------------------------------------------------
# Tổ gia công = GcPartner (gộp đối tác + tổ GC). Danh sách và chi tiết dùng lại
# views_gc_partner; URL cũ của tổ GC (work center) chuyển hướng về đây.
# ---------------------------------------------------------------------------

@login_required
def gc_team_list(request):
    from san_xuat.views_gc_partner import gc_partner_list

    return gc_partner_list(request)


@login_required
def gc_team_create(request):
    return redirect(f"{reverse('san_xuat:gc_team_list')}?add=1")


@login_required
def gc_team_edit(request, pk: int):
    return redirect('san_xuat:gc_partner_detail', pk=pk)


# ---------------------------------------------------------------------------
# Tài khoản đối tác (cổng pn)
# ---------------------------------------------------------------------------

@login_required
def gc_account_list(request):
    from django.utils import timezone

    from san_xuat.forms_gc_partner import GcPartnerAccountForm
    from san_xuat.services.gc_partner import (
        GcPartnerError,
        create_partner_account,
        reset_partner_password,
        toggle_partner_account,
    )

    if not _can_view(request.user):
        return _denied(request)
    can_edit = _can_edit(request.user)
    new_password = None
    account_form = GcPartnerAccountForm(initial={'role': GcPartnerAccount.ROLE_OWNER}) if can_edit else None
    add_partner_id = (request.GET.get('partner') or '').strip()
    show_add_form = False

    if request.method == 'POST':
        if not can_edit:
            return _denied(request)
        action = (request.POST.get('action') or '').strip()
        if action == 'add_account':
            account_form = GcPartnerAccountForm(request.POST)
            add_partner_id = (request.POST.get('partner_id') or '').strip()
            partner = (
                GcPartner.objects.filter(pk=int(add_partner_id), is_active=True).first()
                if add_partner_id.isdigit() else None
            )
            show_add_form = True
            if partner is None:
                messages.error(request, 'Chọn đối tác đang hợp tác cho tài khoản mới.')
            elif account_form.is_valid():
                cd = account_form.cleaned_data
                try:
                    acc, raw = create_partner_account(
                        partner=partner,
                        username=cd['username'],
                        full_name=cd.get('full_name') or '',
                        phone=cd.get('phone') or '',
                        role=cd['role'],
                        password=cd.get('password') or '',
                        created_by=request.user,
                    )
                except GcPartnerError as exc:
                    account_form.add_error('username', str(exc))
                else:
                    new_password = {'username': acc.username, 'password': raw, 'partner': partner.name}
                    messages.success(request, f'Đã tạo tài khoản {acc.username} cho {partner.name}.')
                    account_form = GcPartnerAccountForm(initial={'role': GcPartnerAccount.ROLE_OWNER})
                    show_add_form = False
            else:
                messages.error(request, 'Chưa tạo được tài khoản — kiểm tra lại các ô báo lỗi.')
            action = ''
        acc = (
            get_object_or_404(GcPartnerAccount, pk=request.POST.get('account_id') or 0)
            if action in ('reset_password', 'toggle_account') else None
        )
        if action == 'reset_password':
            raw = reset_partner_password(acc)
            new_password = {'username': acc.username, 'password': raw, 'partner': acc.partner.name}
            messages.success(request, f'Đã đặt lại mật khẩu {acc.username}.')
        elif action == 'toggle_account':
            active = toggle_partner_account(acc)
            messages.success(request, f'{"Mở" if active else "Khóa"} tài khoản {acc.username}.')
            return redirect(request.get_full_path())

    q = (request.GET.get('q') or '').strip()
    partner_raw = (request.GET.get('partner') or '').strip()
    show = (request.GET.get('show') or 'active').strip()
    qs = GcPartnerAccount.objects.select_related('partner', 'created_by').order_by('partner__name', 'username')
    if (request.GET.get('sort') or '').strip():
        qs = apply_sx_list_sort(qs, request, 'gc_account')
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(partner__name__icontains=q)
            | Q(partner__code__icontains=q)
        )
    if partner_raw.isdigit():
        qs = qs.filter(partner_id=int(partner_raw))
    if show == 'active':
        qs = qs.filter(is_active=True)
    elif show == 'inactive':
        qs = qs.filter(is_active=False)
    elif show == 'locked':
        qs = qs.filter(locked_until__gt=timezone.now())
    return render(request, 'san_xuat/gc_account_list.html', {
        **sx_list_grid_context(request, 'gc_account'),
        'accounts': list(qs[:500]),
        'partners': GcPartner.objects.order_by('-is_active', 'name'),
        'search_query': q,
        'partner_filter': partner_raw,
        'show': show,
        'can_edit': can_edit,
        'new_password': new_password,
        'account_form': account_form,
        'active_partners': GcPartner.objects.filter(is_active=True).order_by('name'),
        'add_partner_id': add_partner_id,
        'show_add_form': show_add_form,
    })


# ---------------------------------------------------------------------------
# Thống kê gia công
# ---------------------------------------------------------------------------

def _stats_row_url(row: dict, *, group_by: str, start, end) -> str:
    from san_xuat.services.gc_stats import GROUP_PARTNER

    link = row.get('link') or {}
    if group_by == GROUP_PARTNER and link.get('partner_id'):
        return reverse('san_xuat:gc_partner_detail', args=[link['partner_id']]) + (
            f"?month={start:%Y-%m}"
        )
    params = {k: v for k, v in link.items() if v and k != 'partner_id'}
    if not params:
        return ''
    params.update({'date_from': f'{start:%Y-%m-%d}', 'date_to': f'{end:%Y-%m-%d}'})
    return f"{reverse('san_xuat:subcontract_list')}?{urlencode(params)}"


@login_required
def gc_stats(request):
    from san_xuat.services.gc_stats import GROUP_CHOICES, build_gc_stats

    if not _can_view(request.user):
        return _denied(request)
    report = build_gc_stats(
        month=request.GET.get('month') or '',
        group_by=request.GET.get('by') or '',
    )
    for row in report['rows']:
        row['url'] = _stats_row_url(
            row, group_by=report['group_by'], start=report['start'], end=report['end'],
        )
    return render(request, 'san_xuat/gc_stats.html', {
        'report': report,
        'group_choices': GROUP_CHOICES,
    })


# ---------------------------------------------------------------------------
# KPI gia công (4 chỉ tiêu, hạng A/B/C, chốt tháng)
# ---------------------------------------------------------------------------

@login_required
def gc_kpi(request):
    from san_xuat.services.gc_kpi import KPI_WEIGHTS, current_month, kpi_for_display, lock_kpi

    if not _can_view(request.user):
        return _denied(request)
    can_lock = _can_edit(request.user)
    month = (request.GET.get('month') or request.POST.get('month') or current_month()).strip()

    if request.method == 'POST':
        if not can_lock:
            messages.error(request, 'Bạn không có quyền chốt KPI gia công.')
            return redirect(f"{reverse('san_xuat:gc_kpi')}?{urlencode({'month': month})}")
        raw_ids = request.POST.getlist('partner_id')
        ids = [int(x) for x in raw_ids if str(x).isdigit()]
        partners = GcPartner.objects.filter(pk__in=ids) if ids else GcPartner.objects.filter(is_active=True)
        n = 0
        for partner in partners:
            lock_kpi(partner=partner, month=month, user=request.user)
            n += 1
        messages.success(request, f'Đã chốt KPI tháng {month} cho {n} đối tác.')
        return redirect(f"{reverse('san_xuat:gc_kpi')}?{urlencode({'month': month})}")

    rows = []
    for partner in GcPartner.objects.order_by('-is_active', 'name'):
        kpi = kpi_for_display(partner, month=month)
        has_data = bool(kpi['reported'] or kpi['pending_qty'] or kpi['with_due'] or kpi['plan_qty'] or kpi['sent_orders'])
        if not partner.is_active and not has_data and not kpi['locked']:
            continue
        rows.append({'partner': partner, 'kpi': kpi, 'has_data': has_data})
    month_value = rows[0]['kpi']['month_value'] if rows else month
    return render(request, 'san_xuat/gc_kpi.html', {
        'rows': rows,
        'month': month_value,
        'weights': KPI_WEIGHTS,
        'can_lock': can_lock,
    })
