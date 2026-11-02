"""Quản lý đối tác gia công (GĐ1) trên portal nội bộ."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from hrm.menu_permissions import (
    handle_menu_access_denied,
    user_can_access_menu,
    user_can_create_menu,
    user_can_delete_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.forms_gc_partner import GcPartnerAccountForm, GcPartnerForm, GcPriceRuleForm
from san_xuat.partner_models import GcPartner, GcPartnerAccount, GcPriceRule
from san_xuat.services.gc_partner import (
    GcPartnerError,
    approve_price_rule,
    create_partner_account,
    partner_stats,
    reset_partner_password,
    toggle_partner_account,
)

MENU = 'subcontract'


def _can_view(user) -> bool:
    return any(
        user_can_access_menu(user, MODULE_SAN_XUAT, key)
        for key in (MENU, 'plan_board', 'plan')
    )


def _can_edit(user) -> bool:
    return (
        user_can_create_menu(user, MODULE_SAN_XUAT, MENU)
        or user_can_update_menu(user, MODULE_SAN_XUAT, MENU)
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'plan_board')
    )


def _can_approve_price(user) -> bool:
    return bool(user.is_staff or user_can_delete_menu(user, MODULE_SAN_XUAT, MENU))


def _partner_kpi(partner, month: str) -> dict:
    from san_xuat.services.gc_kpi import kpi_for_display

    return kpi_for_display(partner, month=month)


def _perm(request) -> dict:
    return {
        'can_edit': _can_edit(request.user),
        'can_approve_price': _can_approve_price(request.user),
    }


@login_required
def gc_partner_list(request):
    if not _can_view(request.user):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU)
    q = (request.GET.get('q') or '').strip()
    show = (request.GET.get('show') or 'active').strip()
    qs = GcPartner.objects.annotate(
        n_accounts=Count('accounts', filter=Q(accounts__is_active=True), distinct=True),
        n_orders=Count('subcontract_orders', distinct=True),
        n_prices_pending=Count(
            'price_rules', filter=Q(price_rules__status=GcPriceRule.STATUS_DRAFT), distinct=True,
        ),
    )
    if show == 'active':
        qs = qs.filter(is_active=True)
    elif show == 'inactive':
        qs = qs.filter(is_active=False)
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(phone__icontains=q))
    qs = qs.select_related('created_by').order_by('name', 'code')
    if (request.GET.get('sort') or '').strip():
        from san_xuat.list_grid import apply_sx_list_sort

        qs = apply_sx_list_sort(qs, request, 'gc_partner')

    form = None
    show_add_form = (request.GET.get('add') or '').strip() == '1'
    if _can_edit(request.user):
        if request.method == 'POST':
            form = GcPartnerForm(request.POST)
            if form.is_valid():
                partner = form.save(commit=False)
                partner.created_by = request.user
                partner.team_slugs = form.cleaned_data.get('team_slugs') or []
                partner.save()
                messages.success(request, f'Đã thêm tổ gia công {partner.name}.')
                return redirect('san_xuat:gc_partner_detail', pk=partner.pk)
            messages.error(request, 'Chưa thêm được tổ gia công — kiểm tra lại các ô báo lỗi.')
            show_add_form = True
        else:
            form = GcPartnerForm(initial={'is_active': True})
    from san_xuat.list_grid import sx_list_grid_context

    return render(request, 'san_xuat/gc_partner_list.html', {
        **_perm(request),
        **sx_list_grid_context(request, 'gc_partner'),
        'partners': qs,
        'show_add_form': show_add_form,
        'form': form,
        'search_query': q,
        'show': show,
    })


@login_required
def gc_partner_detail(request, pk: int):
    if not _can_view(request.user):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU)
    partner = get_object_or_404(GcPartner, pk=pk)
    can_edit = _can_edit(request.user)
    can_approve = _can_approve_price(request.user)

    partner_form = GcPartnerForm(instance=partner)
    account_form = GcPartnerAccountForm()
    price_form = GcPriceRuleForm(partner=partner, initial={'valid_from': timezone.localdate()})
    new_password = None

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if not can_edit and action != 'approve_price':
            return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU)

        if action == 'update_partner':
            partner_form = GcPartnerForm(request.POST, instance=partner)
            if partner_form.is_valid():
                obj = partner_form.save(commit=False)
                obj.team_slugs = partner_form.cleaned_data.get('team_slugs') or []
                obj.save()
                messages.success(request, 'Đã cập nhật thông tin tổ gia công.')
                return redirect('san_xuat:gc_partner_detail', pk=partner.pk)
            messages.error(request, 'Chưa lưu được — kiểm tra lại các ô báo lỗi.')

        elif action == 'add_account':
            account_form = GcPartnerAccountForm(request.POST)
            if account_form.is_valid():
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
                    new_password = {'username': acc.username, 'password': raw}
                    account_form = GcPartnerAccountForm()
                    messages.success(request, f'Đã tạo tài khoản {acc.username}.')

        elif action in {'reset_password', 'toggle_account'}:
            acc = get_object_or_404(GcPartnerAccount, pk=request.POST.get('account_id'), partner=partner)
            if action == 'reset_password':
                raw = reset_partner_password(acc)
                new_password = {'username': acc.username, 'password': raw}
                messages.success(request, f'Đã đặt lại mật khẩu {acc.username}.')
            else:
                active = toggle_partner_account(acc)
                messages.success(request, f'{"Mở" if active else "Khóa"} tài khoản {acc.username}.')
                return redirect('san_xuat:gc_partner_detail', pk=partner.pk)

        elif action == 'add_price':
            price_form = GcPriceRuleForm(request.POST, partner=partner)
            if price_form.is_valid():
                rule = price_form.save(commit=False)
                rule.partner = partner
                rule.created_by = request.user
                rule.status = GcPriceRule.STATUS_DRAFT
                rule.save()
                messages.success(request, 'Đã thêm giá — chờ duyệt.')
                return redirect('san_xuat:gc_partner_detail', pk=partner.pk)
            messages.error(request, 'Chưa thêm được giá — kiểm tra lại.')

        elif action == 'approve_price':
            if not can_approve:
                messages.error(request, 'Bạn không có quyền duyệt giá gia công.')
            else:
                rule = get_object_or_404(GcPriceRule, pk=request.POST.get('rule_id'), partner=partner)
                try:
                    approve_price_rule(rule, user=request.user)
                except GcPartnerError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, 'Đã duyệt giá.')
            return redirect('san_xuat:gc_partner_detail', pk=partner.pk)

        elif action == 'delete_price':
            rule = get_object_or_404(GcPriceRule, pk=request.POST.get('rule_id'), partner=partner)
            if rule.status == GcPriceRule.STATUS_APPROVED and not can_approve:
                messages.error(request, 'Giá đã duyệt — chỉ người duyệt giá được xóa.')
            else:
                rule.delete()
                messages.success(request, 'Đã xóa dòng giá.')
            return redirect('san_xuat:gc_partner_detail', pk=partner.pk)

        elif action == 'end_price':
            rule = get_object_or_404(GcPriceRule, pk=request.POST.get('rule_id'), partner=partner)
            if not can_approve:
                messages.error(request, 'Bạn không có quyền chốt hết hiệu lực giá.')
            else:
                today = timezone.localdate()
                rule.valid_to = max(rule.valid_from, today)
                rule.save(update_fields=['valid_to'])
                messages.success(request, f'Giá hết hiệu lực từ sau {rule.valid_to:%d/%m/%Y}.')
            return redirect('san_xuat:gc_partner_detail', pk=partner.pk)

    from san_xuat.hub_models import SxSubcontractOrder

    recent_orders = (
        SxSubcontractOrder.objects.filter(partner=partner)
        .select_related('production_order')
        .order_by('-order_date', '-pk')[:20]
    )
    return render(request, 'san_xuat/gc_partner_detail.html', {
        **_perm(request),
        'partner': partner,
        'partner_form': partner_form,
        'account_form': account_form,
        'price_form': price_form,
        'accounts': partner.accounts.order_by('-is_active', 'username'),
        'price_rules': partner.price_rules.select_related('approved_by').order_by(
            'team_slug', 'product_code', '-valid_from',
        ),
        'recent_orders': recent_orders,
        'stats': partner_stats(partner),
        'kpi': _partner_kpi(partner, request.GET.get('month') or ''),
        'activities': partner.activities.select_related('account', 'order').order_by('-created_at', '-pk')[:30],
        'new_password': new_password,
        'today': timezone.localdate(),
    })


def _can_review_output(user) -> bool:
    return bool(
        user.is_staff
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'qc')
        or user_can_update_menu(user, MODULE_SAN_XUAT, 'qc_sheet')
    )


@login_required
def gc_output_review(request):
    """QC duyệt báo sản lượng đối tác → ghi tiến độ tổ thuê."""
    from decimal import Decimal

    from san_xuat.partner_models import GcOutputReport
    from san_xuat.services.gc_output import (
        GcOutputError,
        approve_report,
        reject_report,
        unapprove_report,
    )

    if not (_can_view(request.user) or _can_review_output(request.user)):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU)
    can_review = _can_review_output(request.user)
    status = (request.GET.get('status') or 'submitted').strip()
    partner_id = (request.GET.get('partner') or '').strip()

    if request.method == 'POST':
        if not can_review:
            messages.error(request, 'Bạn không có quyền duyệt sản lượng gia công.')
            return redirect(request.get_full_path())
        action = (request.POST.get('action') or '').strip()
        rid = int(request.POST.get('report_id') or 0)
        note = request.POST.get('note') or ''
        try:
            if action == 'approve':
                sizes = {
                    key[5:]: (request.POST.get(key) or '0').strip() or '0'
                    for key in request.POST if key.startswith('size_')
                }
                r = approve_report(report_id=rid, user=request.user, size_qtys=sizes, note=note)
                messages.success(request, f'Đã duyệt {r.approved_qty:,.0f} SP — {r.order.code}.')
            elif action == 'reject':
                r = reject_report(report_id=rid, user=request.user, note=note)
                messages.success(request, f'Đã từ chối báo cáo {r.order.code}.')
            elif action == 'unapprove':
                r = unapprove_report(report_id=rid, user=request.user)
                messages.success(request, f'Đã huỷ duyệt — {r.order.code} trừ lại tiến độ.')
        except (GcOutputError, GcOutputReport.DoesNotExist) as exc:
            messages.error(request, str(exc) or 'Không tìm thấy báo cáo.')
        return redirect(request.get_full_path())

    qs = GcOutputReport.objects.select_related(
        'order', 'order__production_order', 'partner', 'account', 'reviewed_by',
    )
    if status in {'submitted', 'approved', 'rejected', 'cancelled'}:
        qs = qs.filter(status=status)
    if partner_id.isdigit():
        qs = qs.filter(partner_id=int(partner_id))
    from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context

    if (request.GET.get('sort') or '').strip():
        ordered = apply_sx_list_sort(qs, request, 'gc_output')
    elif status == 'submitted':
        ordered = qs.order_by('work_date', 'pk')
    else:
        ordered = qs.order_by('-reviewed_at', '-pk')
    rows = []
    for r in ordered[:300]:
        sizes = [(k, Decimal(str(v))) for k, v in (r.size_qtys or {}).items()]
        posted_qty = sum((Decimal(str(v)) for v in (r.progress_posted or {}).values()), Decimal('0'))
        rows.append({'report': r, 'sizes': sizes, 'posted_qty': posted_qty})
    return render(request, 'san_xuat/gc_output_review.html', {
        **_perm(request),
        **sx_list_grid_context(request, 'gc_output'),
        'can_review': can_review,
        'rows': rows,
        'status': status,
        'partner_id': partner_id,
        'partners': GcPartner.objects.filter(is_active=True).order_by('name'),
        'pending_count': GcOutputReport.objects.filter(status='submitted').count(),
    })
