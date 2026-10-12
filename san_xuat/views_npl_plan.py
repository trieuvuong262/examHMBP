"""Kế hoạch Nguyên Phụ Liệu — trang tổng quan các bước so giá → đặt hàng → hàng về."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.menu_permissions import handle_menu_access_denied, user_can_access_menu, user_can_create_menu
from hrm.module_permissions import MODULE_KHO_NPL, MODULE_SAN_XUAT
from san_xuat.hub_models import (
    SxNplPurchaseRequest,
    SxNplQuoteSheet,
    SxPurchaseOrder,
    SxSalesOrder,
)

NPL_PLAN_MENU_KEYS = ('sx_price_quote', 'sx_price_approve', 'npl_pr', 'plan_npl', 'purchase_order')

UPCOMING_DAYS = 3
LIST_LIMIT = 15

_OPEN_PLAN_STATUSES = (
    SxSalesOrder.PLAN_QUEUED,
    SxSalesOrder.PLAN_RANKED,
    SxSalesOrder.PLAN_RELEASED,
    SxSalesOrder.PLAN_IN_PROGRESS,
    SxSalesOrder.PLAN_ON_HOLD,
)


def npl_plan_menu_access(user) -> dict[str, bool]:
    return {key: user_can_access_menu(user, MODULE_SAN_XUAT, key) for key in NPL_PLAN_MENU_KEYS}


def _status_counts(model) -> dict[str, int]:
    rows = model.objects.filter(is_demo=False).order_by().values('status').annotate(n=Count('pk'))
    return {row['status']: row['n'] for row in rows}


def _step_cards(access: dict[str, bool]) -> list[dict]:
    pr_counts = _status_counts(SxNplPurchaseRequest)
    cards = []
    if access['sx_price_quote'] or access['sx_price_approve']:
        quote_counts = _status_counts(SxNplQuoteSheet)
        if access['sx_price_quote']:
            cards.append({
                'label': 'Bảng so giá đang soạn',
                'count': quote_counts.get(SxNplQuoteSheet.STATUS_DRAFT, 0),
                'icon': 'bi-tags',
                'href': reverse('san_xuat:price_quote_list'),
            })
        cards.append({
            'label': 'Bảng so giá chờ chốt',
            'count': quote_counts.get(SxNplQuoteSheet.STATUS_SUBMITTED, 0),
            'icon': 'bi-hourglass-split',
            'href': reverse(
                'san_xuat:price_approve_home' if access['sx_price_approve'] else 'san_xuat:price_quote_list'
            ),
        })
    if access['npl_pr']:
        cards.append({
            'label': 'Đơn đặt hàng nháp',
            'count': pr_counts.get(SxNplPurchaseRequest.STATUS_DRAFT, 0),
            'icon': 'bi-cart-plus',
            'href': reverse('san_xuat:npl_purchase_request'),
        })
    if access['npl_pr'] or access['sx_price_approve']:
        cards.append({
            'label': 'Đơn chờ duyệt giá',
            'count': pr_counts.get(SxNplPurchaseRequest.STATUS_PRICE_REVIEW, 0),
            'icon': 'bi-shield-check',
            'href': reverse(
                'san_xuat:price_approve_home' if access['sx_price_approve'] else 'san_xuat:npl_purchase_request'
            ),
        })
    if access['plan_npl'] or access['npl_pr']:
        cards.append({
            'label': 'Chờ xác nhận đặt hàng',
            'count': (
                pr_counts.get(SxNplPurchaseRequest.STATUS_PRICED, 0)
                + pr_counts.get(SxNplPurchaseRequest.STATUS_SUBMITTED, 0)
            ),
            'icon': 'bi-check2-square',
            'href': reverse('san_xuat:plan_npl'),
        })
        cards.append({
            'label': 'Chờ hàng về',
            'count': SxPurchaseOrder.objects.filter(
                is_demo=False, status=SxPurchaseOrder.STATUS_CONFIRMED,
            ).count(),
            'icon': 'bi-truck',
            'href': reverse('san_xuat:plan_npl_confirmed'),
        })
    return cards


def _shortage_orders(user) -> list[dict]:
    can_place = user_can_create_menu(user, MODULE_SAN_XUAT, 'npl_pr')
    can_view_board = (
        user_can_access_menu(user, MODULE_SAN_XUAT, 'plan_board')
        or user_can_access_menu(user, MODULE_SAN_XUAT, 'plan')
    )
    board_url = reverse('san_xuat:plan_board')
    orders = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status__in=_OPEN_PLAN_STATUSES,
            npl_lines__qty_shortfall__gt=0,
        )
        .annotate(
            short_count=Count('npl_lines', filter=Q(npl_lines__qty_shortfall__gt=0), distinct=True),
        )
        .order_by('due_date', 'pk')
    )
    rows = []
    for order in orders[:LIST_LIMIT]:
        rows.append({
            'order': order,
            'short_count': order.short_count,
            'board_url': (
                f'{board_url}?mode=list&tab=queue&q={quote(order.code)}&npl={order.pk}' if can_view_board else ''
            ),
            'shortage_url': (
                reverse('san_xuat:plan_shortage_order', args=[order.pk]) if can_place else ''
            ),
        })
    return rows


def _shortage_order_total() -> int:
    return (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status__in=_OPEN_PLAN_STATUSES,
            npl_lines__qty_shortfall__gt=0,
        )
        .distinct()
        .count()
    )


def _due_purchase_orders(access: dict[str, bool]) -> tuple[list[dict], int, int]:
    today = timezone.localdate()
    horizon = today + timedelta(days=UPCOMING_DAYS)
    qs = (
        SxPurchaseOrder.objects.filter(
            is_demo=False,
            status=SxPurchaseOrder.STATUS_CONFIRMED,
            expected_date__isnull=False,
            expected_date__lte=horizon,
        )
        .select_related('purchase_request__sales_order', 'supplier')
        .annotate(qty_total=Sum('lines__qty_ordered'))
        .order_by('expected_date', 'pk')
    )
    late_count = qs.filter(expected_date__lt=today).count()
    upcoming_count = qs.filter(expected_date__gte=today).count()
    confirmed_url = reverse('san_xuat:plan_npl_confirmed')
    rows = []
    for po in qs[:LIST_LIMIT]:
        order = po.purchase_request.sales_order if po.purchase_request_id else None
        if access['plan_npl'] or access['npl_pr']:
            href = f'{confirmed_url}?dh={order.pk}' if order else confirmed_url
        elif access['purchase_order']:
            href = reverse('san_xuat:purchase_order_detail', args=[po.pk])
        else:
            href = ''
        rows.append({
            'po': po,
            'order': order,
            'supplier': (po.supplier.name if po.supplier_id else '') or po.supplier_name or '—',
            'qty_total': po.qty_total or Decimal('0'),
            'is_late': po.expected_date < today,
            'days': abs((po.expected_date - today).days),
            'href': href,
        })
    return rows, late_count, upcoming_count


def _low_stock_summary(user) -> dict | None:
    if not user_can_access_menu(user, MODULE_KHO_NPL, 'material_stock'):
        return None
    from kho_npl.choices import STOCK_STATUS_LOW, STOCK_STATUS_OUT
    from kho_npl.services.stock import material_stock_rows

    low = out = 0
    for row in material_stock_rows():
        if row['status'] == STOCK_STATUS_LOW:
            low += 1
        elif row['status'] == STOCK_STATUS_OUT:
            out += 1
    alerts_url = reverse('kho_npl:stock_alerts')
    return {
        'low': low,
        'out': out,
        'low_url': f'{alerts_url}?status={STOCK_STATUS_LOW}',
        'out_url': f'{alerts_url}?status={STOCK_STATUS_OUT}',
    }


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_plan_home(request):
    access = npl_plan_menu_access(request.user)
    if not any(access.values()):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'npl_pr')

    show_orders = access['npl_pr'] or access['plan_npl']
    due_rows, late_count, upcoming_count = (
        _due_purchase_orders(access) if show_orders else ([], 0, 0)
    )
    can_view_board = (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan_board')
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan')
    )
    board_url = reverse('san_xuat:plan_board')
    return render(request, 'san_xuat/npl_plan_home.html', {
        'page_title': 'Kế hoạch Nguyên Phụ Liệu',
        'access': access,
        'can_create_quote': user_can_create_menu(request.user, MODULE_SAN_XUAT, 'sx_price_quote'),
        'board_queue_url': f'{board_url}?mode=list&tab=queue' if can_view_board else '',
        'board_short_url': f'{board_url}?mode=list&tab=queue&npl_status=short' if can_view_board else '',
        'step_cards': _step_cards(access),
        'show_orders': show_orders,
        'shortage_rows': _shortage_orders(request.user) if show_orders else [],
        'shortage_total': _shortage_order_total() if show_orders else 0,
        'due_rows': due_rows,
        'late_count': late_count,
        'upcoming_count': upcoming_count,
        'upcoming_days': UPCOMING_DAYS,
        'low_stock': _low_stock_summary(request.user),
    })
