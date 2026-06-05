"""Tra cứu đơn đặt hàng & hóa đơn — đọc từ mirror kv_*."""

from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .browse import KV_PAGE_SIZE, get_page_number, paginate_api_meta
from . import local_lookup as local
from .formatters import (
    format_invoice_detail,
    format_invoice_row,
    format_order_detail,
    format_order_row,
)
from .decorators import kiotviet_access_required
from .sync_service import current_retailer
from .views import MIRROR_EMPTY_HINT


def _transaction_lookup(
    request,
    *,
    title: str,
    icon: str,
    template_name: str,
    detail_url_name: str,
    empty_hint: str,
    type_options: tuple,
    mirror_entity: str,
    browse_fn,
    get_code_fn,
    format_row_fn,
):
    search_type = (request.GET.get('type') or 'code').strip()
    allowed = {opt[0] for opt in type_options}
    if search_type not in allowed:
        search_type = type_options[0][0]
    query = get_search_query(request)
    items: list[dict] = []
    total = 0
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)
    retailer = current_retailer()

    if browse_mode:
        rows, total = browse_fn(page=page, per_page=KV_PAGE_SIZE, retailer=retailer)
    elif search_type == 'code':
        detail = get_code_fn(retailer, query)
        if detail:
            rows, total = [detail], 1
        else:
            rows, total = browse_fn(page=page, per_page=KV_PAGE_SIZE, code=query, retailer=retailer)
    else:
        rows, total = browse_fn(
            page=page, per_page=KV_PAGE_SIZE, customer_code=query, retailer=retailer,
        )
    items = [format_row_fn(r) for r in rows]

    if total and (browse_mode or query):
        page_obj, query_string = paginate_api_meta(request, total)

    return render(
        request,
        template_name,
        _lookup_context(
            request,
            title=title,
            icon=icon,
            search_type=search_type,
            search_query=query,
            items=items,
            total=total,
            api_error=None,
            mirror_empty_hint=MIRROR_EMPTY_HINT if total == 0 else '',
            detail_url_name=detail_url_name,
            empty_hint=empty_hint,
            type_options=type_options,
            page_obj=page_obj,
            query_string=query_string,
            browse_mode=browse_mode,
            items_count=len(items),
            mirror_entity=mirror_entity,
        ),
    )


@kiotviet_access_required
def order_lookup(request):
    return _transaction_lookup(
        request,
        title='Tra cứu đơn đặt hàng',
        icon='bi-cart-check',
        template_name='kiotviet/order_lookup.html',
        detail_url_name='kiotviet:order_detail',
        empty_hint='Nhập mã đơn hoặc mã khách hàng để lọc. Không nhập từ khóa: xem 30 đơn mới nhất.',
        type_options=(
            ('code', 'Mã đơn đặt hàng'),
            ('customer_code', 'Mã khách hàng'),
        ),
        mirror_entity='orders',
        browse_fn=local.browse_orders,
        get_code_fn=local.get_order_by_code,
        format_row_fn=format_order_row,
    )


@kiotviet_access_required
def order_detail(request, order_id: int):
    retailer = current_retailer()
    raw = local.get_order(retailer, order_id)
    if raw is None:
        messages.error(request, 'Không tìm thấy đơn đặt hàng trong dữ liệu đã sync.')
        return redirect('kiotviet:order_lookup')
    return render(
        request,
        'kiotviet/_transaction_detail.html',
        {
            'doc': format_order_detail(raw),
            'header_icon': 'bi-cart-check',
            'back_url_name': 'kiotviet:order_lookup',
        },
    )


@kiotviet_access_required
def invoice_lookup(request):
    return _transaction_lookup(
        request,
        title='Tra cứu hóa đơn',
        icon='bi-receipt',
        template_name='kiotviet/invoice_lookup.html',
        detail_url_name='kiotviet:invoice_detail',
        empty_hint='Nhập mã hóa đơn hoặc mã khách hàng để lọc. Không nhập từ khóa: xem 30 hóa đơn mới nhất.',
        type_options=(
            ('code', 'Mã hóa đơn'),
            ('customer_code', 'Mã khách hàng'),
        ),
        mirror_entity='invoices',
        browse_fn=local.browse_invoices,
        get_code_fn=local.get_invoice_by_code,
        format_row_fn=format_invoice_row,
    )


@kiotviet_access_required
def invoice_detail(request, invoice_id: int):
    retailer = current_retailer()
    raw = local.get_invoice(retailer, invoice_id)
    if raw is None:
        messages.error(request, 'Không tìm thấy hóa đơn trong dữ liệu đã sync.')
        return redirect('kiotviet:invoice_lookup')
    return render(
        request,
        'kiotviet/_transaction_detail.html',
        {
            'doc': format_invoice_detail(raw),
            'header_icon': 'bi-receipt',
            'back_url_name': 'kiotviet:invoice_lookup',
        },
    )


def _lookup_context(request, **extra) -> dict:
    extra.setdefault('retailer', current_retailer())
    return extra
