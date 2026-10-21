"""Kế hoạch Nguyên Phụ Liệu — trang tổng quan các bước so giá → đặt hàng → hàng về."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.menu_permissions import (
    handle_menu_access_denied,
    user_can_access_menu,
    user_can_create_menu,
    user_can_update_menu,
)
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
                'label': 'Báo giá đang soạn',
                'count': quote_counts.get(SxNplQuoteSheet.STATUS_DRAFT, 0),
                'icon': 'bi-tags',
                'href': reverse('san_xuat:price_quote_list'),
            })
        cards.append({
            'label': 'Báo giá chờ chốt',
            'count': quote_counts.get(SxNplQuoteSheet.STATUS_SUBMITTED, 0),
            'icon': 'bi-hourglass-split',
            'href': reverse(
                'san_xuat:price_approve_home' if access['sx_price_approve'] else 'san_xuat:price_quote_list'
            ),
        })
    if access['npl_pr']:
        cards.append({
            'label': 'Đề nghị mua nháp',
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
            'href': reverse('san_xuat:npl_goods_receipt'),
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
    rows = []
    for po in qs[:LIST_LIMIT]:
        order = po.purchase_request.sales_order if po.purchase_request_id else None
        if access['purchase_order'] or access['plan_npl'] or access['npl_pr']:
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

    show_orders = access['npl_pr'] or access['plan_npl'] or access['purchase_order']
    due_rows, late_count, upcoming_count = (
        _due_purchase_orders(access) if show_orders else ([], 0, 0)
    )
    can_view_board = (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan_board')
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan')
    )
    board_url = reverse('san_xuat:plan_board')
    return render(request, 'san_xuat/npl_plan_home.html', {
        'page_title': 'Theo dõi và báo cáo mua hàng',
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
        'open_po_count': _open_po_count() if show_orders else 0,
        'unconfirmed_po_count': _unconfirmed_po_count() if show_orders else 0,
        'price_rows': _recent_prices() if show_orders or access['sx_price_quote'] or access['sx_price_approve'] else [],
        'supplier_rows': _supplier_performance() if show_orders else [],
        'watch': _purchase_watch(request) if show_orders else None,
    })


def _deny_unless(request, *keys: str):
    if any(user_can_access_menu(request.user, MODULE_SAN_XUAT, key) for key in keys):
        return None
    return handle_menu_access_denied(request, MODULE_SAN_XUAT, keys[0])


def _open_po_count() -> int:
    return SxPurchaseOrder.objects.filter(
        is_demo=False, status=SxPurchaseOrder.STATUS_CONFIRMED,
    ).count()


def _unconfirmed_po_count() -> int:
    return SxPurchaseOrder.objects.filter(
        is_demo=False,
        status=SxPurchaseOrder.STATUS_CONFIRMED,
        supplier_confirm_status=SxPurchaseOrder.CONFIRM_PENDING,
    ).count()


def _recent_prices() -> list[dict]:
    from san_xuat.hub_models import SxNplQuoteOffer

    rows = []
    offers = (
        SxNplQuoteOffer.objects.filter(
            is_chosen=True,
            sheet__status='decided',
            sheet__is_demo=False,
        )
        .select_related('supplier', 'sheet', 'material')
        .order_by('-sheet__decided_at', '-id')[:12]
    )
    for offer in offers:
        image_url = ''
        mat = offer.material
        if mat and mat.image:
            try:
                image_url = mat.image.url
            except (ValueError, OSError):
                image_url = ''
        rows.append({
            'code': offer.material_code,
            'name': offer.material_name,
            'image_url': image_url,
            'material_id': offer.material_id,
            'supplier': offer.supplier.name if offer.supplier_id else '—',
            'price': offer.unit_price,
            'when': offer.sheet.decided_at,
            'href': reverse('san_xuat:price_quote_detail', args=[offer.sheet_id]),
        })
    return rows


def _supplier_performance() -> list[dict]:
    today = timezone.localdate()
    stats = (
        SxPurchaseOrder.objects.filter(is_demo=False)
        .exclude(status=SxPurchaseOrder.STATUS_CANCELLED)
        .values('supplier_name')
        .annotate(
            po_count=Count('pk'),
            open_count=Count('pk', filter=Q(status=SxPurchaseOrder.STATUS_CONFIRMED)),
            late_count=Count(
                'pk',
                filter=Q(status=SxPurchaseOrder.STATUS_CONFIRMED, expected_date__lt=today),
            ),
            received_count=Count('pk', filter=Q(status=SxPurchaseOrder.STATUS_RECEIVED)),
        )
        .order_by('-po_count', 'supplier_name')[:12]
    )
    return [
        {
            'supplier': row['supplier_name'] or '—',
            'po_count': row['po_count'],
            'open_count': row['open_count'],
            'late_count': row['late_count'],
            'received_count': row['received_count'],
        }
        for row in stats
    ]


def _purchase_watch(request) -> dict:
    """Danh sách theo dõi lấy từ dữ liệu thật. Bộ lọc để trống thì không cắt bớt."""
    from san_xuat.hub_models import SxNplQuoteOffer, SxPurchaseOrderLine

    department = (request.GET.get('department') or '').strip()
    material = (request.GET.get('material') or '').strip()
    status = (request.GET.get('status') or '').strip()
    today = timezone.localdate()
    soon = today + timedelta(days=3)

    waiting_pr = SxNplPurchaseRequest.objects.filter(
        is_demo=False, status=SxNplPurchaseRequest.STATUS_SUBMITTED,
    )
    if department:
        waiting_pr = waiting_pr.filter(department_name__icontains=department)
    if material:
        waiting_pr = waiting_pr.filter(lines__material_code__icontains=material)
    waiting_pr = list(waiting_pr.distinct().order_by('-id')[:20])

    open_rfq = (
        SxNplQuoteSheet.objects.filter(is_demo=False, status=SxNplQuoteSheet.STATUS_DRAFT)
        .annotate(offer_count=Count('offers'))
        .filter(Q(offer_count=0) | Q(response_due__isnull=False, response_due__lte=soon))
        .order_by('response_due', '-id')[:20]
    )
    waiting_price = list(
        SxNplQuoteSheet.objects.filter(is_demo=False, status=SxNplQuoteSheet.STATUS_SUBMITTED)
        .order_by('-id')[:20]
    )
    po_qs = (
        SxPurchaseOrder.objects.filter(is_demo=False)
        .exclude(status=SxPurchaseOrder.STATUS_CANCELLED)
        .select_related('supplier')
        .prefetch_related('lines')
    )
    if status in dict(SxPurchaseOrder.STATUS_CHOICES):
        po_qs = po_qs.filter(status=status)
    if material:
        po_qs = po_qs.filter(lines__material_code__icontains=material)
    po_list = list(po_qs.distinct().order_by('-id')[:40])
    watch_codes = {
        (ln.material_code or '').strip()
        for po in po_list
        for ln in po.lines.all()
        if (ln.material_code or '').strip()
    }
    from kho_npl.models import Material
    watch_materials = {
        (m.code or '').strip().casefold(): m
        for m in Material.objects.filter(code__in=watch_codes)
    }
    line_rows = []
    for po in po_list:
        for ln in po.lines.all():
            if material and material.casefold() not in (ln.material_code or '').casefold():
                continue
            mat = watch_materials.get((ln.material_code or '').strip().casefold())
            image_url = ''
            if mat and mat.image:
                try:
                    image_url = mat.image.url
                except (ValueError, OSError):
                    image_url = ''
            line_rows.append({
                'po': po,
                'code': ln.material_code,
                'name': ln.material_name,
                'image_url': image_url,
                'material_id': mat.pk if mat else None,
                'ordered': ln.qty_ordered,
                'received': ln.qty_received,
                'qc_pass': ln.qty_qc_pass,
                'qc_fail': ln.qty_qc_fail,
                'returned': ln.qty_returned,
                'remaining': ln.qty_remaining,
            })
            if len(line_rows) >= 40:
                break
        if len(line_rows) >= 40:
            break
    qc_rows = (
        SxPurchaseOrderLine.objects.filter(order__is_demo=False)
        .exclude(order__status=SxPurchaseOrder.STATUS_CANCELLED)
        .values('order__supplier_name')
        .annotate(
            received=Sum('qty_received'),
            passed=Sum('qty_qc_pass'),
            failed=Sum('qty_qc_fail'),
            returned=Sum('qty_returned'),
        )
        .order_by('order__supplier_name')[:20]
    )
    price_history = (
        SxNplQuoteOffer.objects.filter(is_chosen=True, sheet__is_demo=False, sheet__status='decided')
        .select_related('supplier', 'sheet', 'material')
        .order_by('-sheet__decided_at', '-id')
    )
    if material:
        price_history = price_history.filter(material_code__icontains=material)
    return {
        'department': department,
        'material': material,
        'status': status,
        'status_choices': SxPurchaseOrder.STATUS_CHOICES,
        'waiting_pr': waiting_pr,
        'open_rfq': list(open_rfq),
        'waiting_price': waiting_price,
        'line_rows': line_rows,
        'qc_rows': list(qc_rows),
        'price_history': list(price_history[:20]),
    }


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_buy_plan(request):
    """Nhu cầu thiếu theo mã NPL, màu, quy cách và ngày cần."""
    denied = _deny_unless(request, 'plan_npl', 'npl_pr')
    if denied:
        return denied
    from kho_npl.catalog_labels import color_label, spec_label
    from kho_npl.models import Material
    from san_xuat.hub_models import SxOrderNplLine
    from san_xuat.services.npl_buy import create_pr_from_npl_lines
    from san_xuat.services.planning import PlanningError

    can_create = user_can_create_menu(request.user, MODULE_SAN_XUAT, 'npl_pr') or user_can_update_menu(
        request.user, MODULE_SAN_XUAT, 'npl_pr',
    )
    if request.method == 'POST':
        if not can_create:
            messages.error(request, 'Không có quyền lập đề nghị mua.')
            return redirect('san_xuat:npl_buy_plan')
        try:
            created = create_pr_from_npl_lines(
                line_ids=request.POST.getlist('line_id'),
                user=request.user,
                reason=request.POST.get('reason') or '',
            )
        except PlanningError as exc:
            messages.error(request, str(exc))
            return redirect('san_xuat:npl_buy_plan')
        messages.success(request, f'Đã lập {len(created)} đề nghị mua.')
        if len(created) == 1:
            return redirect('san_xuat:npl_purchase_request_detail', pk=created[0].pk)
        return redirect('san_xuat:npl_purchase_request')

    lines = (
        SxOrderNplLine.objects.filter(
            qty_shortfall__gt=0,
            order__is_demo=False,
            order__confirm_status='confirmed',
        )
        .select_related('order')
        .order_by('ready_date', 'material_code', 'id')[:200]
    )
    codes = {(ln.material_code or '').strip() for ln in lines}
    materials = {
        (m.code or '').strip().casefold(): m
        for m in Material.objects.filter(code__in=codes).select_related('color', 'specification', 'unit')
    }
    rows = []
    for ln in lines:
        mat = materials.get((ln.material_code or '').strip().casefold())
        image_url = ''
        if mat and mat.image:
            try:
                image_url = mat.image.url
            except (ValueError, OSError):
                image_url = ''
        rows.append({
            'line': ln,
            'color': color_label(mat.color) if mat and mat.color_id else '',
            'spec': spec_label(mat.specification) if mat and mat.specification_id else '',
            'unit': ln.unit or '',
            'image_url': image_url,
            'material_id': mat.pk if mat else None,
        })
    return render(request, 'san_xuat/npl_buy_plan.html', {
        'page_title': 'Kế hoạch mua hàng',
        'rows': rows,
        'can_create': can_create,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_supplier_confirm(request):
    """Submenu 06 — đơn đã phát hành, chờ hoặc đã có xác nhận nhà cung cấp."""
    denied = _deny_unless(request, 'purchase_order', 'plan_npl')
    if denied:
        return denied
    orders = (
        SxPurchaseOrder.objects.filter(
            is_demo=False, status=SxPurchaseOrder.STATUS_CONFIRMED,
        )
        .select_related('supplier', 'purchase_request')
        .order_by('supplier_confirm_status', 'expected_date', 'pk')
    )
    return render(request, 'san_xuat/npl_supplier_confirm.html', {
        'page_title': 'Xác nhận nhà cung cấp',
        'orders': orders[:80],
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_goods_receipt(request):
    """Submenu 07 — nhận các đợt còn lại và ghi sổ toàn bộ số nhận."""
    denied = _deny_unless(request, 'purchase_order', 'plan_npl', 'npl_pr')
    if denied:
        return denied
    rows = []
    orders = (
        SxPurchaseOrder.objects.filter(
            is_demo=False, status=SxPurchaseOrder.STATUS_CONFIRMED,
        )
        .select_related('supplier')
        .prefetch_related('lines')
        .order_by('expected_date', 'pk')
    )
    for po in orders[:80]:
        remaining = sum((ln.qty_remaining for ln in po.lines.all()), Decimal('0'))
        if remaining <= 0:
            continue
        rows.append({
            'po': po,
            'supplier': (po.supplier.name if po.supplier_id else '') or po.supplier_name or '—',
            'remaining': remaining,
            'late': bool(po.expected_date and po.expected_date < timezone.localdate()),
        })
    return render(request, 'san_xuat/npl_goods_receipt.html', {
        'page_title': 'Nhận hàng và nhập kho',
        'rows': rows,
    })
