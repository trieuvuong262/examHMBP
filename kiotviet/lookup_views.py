"""Tra cứu đơn đặt hàng & hóa đơn — logic dùng chung."""

from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .browse import fetch_api_page, get_page_number, paginate_api_meta
from .client import KiotVietAPIError, KiotVietClient
from .formatters import (
    format_invoice_detail,
    format_invoice_row,
    format_order_detail,
    format_order_row,
)
from .decorators import kiotviet_access_required


def _list_params(search_type: str, query: str) -> dict:
    params = {
        'orderDirection': 'Desc',
        'orderBy': 'purchaseDate',
    }
    if search_type == 'customer_code' and query:
        params['customerCode'] = query
    return params


def _transaction_lookup(
    request,
    *,
    title: str,
    icon: str,
    template_name: str,
    detail_url_name: str,
    empty_hint: str,
    type_options: tuple,
    list_fn,
    get_by_code_fn,
    format_row_fn,
):
    search_type = (request.GET.get('type') or 'code').strip()
    allowed = {opt[0] for opt in type_options}
    if search_type not in allowed:
        search_type = type_options[0][0]
    query = get_search_query(request)
    items: list[dict] = []
    total = 0
    api_error = None
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)

    client = KiotVietClient()
    base_params = _list_params(search_type, query)

    try:
        if browse_mode:
            rows, total = fetch_api_page(list_fn, base_params, page)
            items = [format_row_fn(r) for r in rows]
        elif search_type == 'code':
            try:
                detail = get_by_code_fn(query)
                items = [format_row_fn(detail)]
                total = 1
            except KiotVietAPIError as exc:
                if exc.status_code != 404:
                    raise
                rows, total = fetch_api_page(list_fn, base_params, page)
                items = [format_row_fn(r) for r in rows]
        else:
            rows, total = fetch_api_page(list_fn, _list_params('customer_code', query), page)
            items = [format_row_fn(r) for r in rows]
    except KiotVietAPIError as exc:
        api_error = str(exc)
        messages.error(request, api_error)

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
            api_error=api_error,
            detail_url_name=detail_url_name,
            empty_hint=empty_hint,
            type_options=type_options,
            page_obj=page_obj,
            query_string=query_string,
            browse_mode=browse_mode,
            items_count=len(items),
        ),
    )


@kiotviet_access_required
def order_lookup(request):
    client = KiotVietClient()
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
        list_fn=client.list_orders,
        get_by_code_fn=client.get_order_by_code,
        format_row_fn=format_order_row,
    )


@kiotviet_access_required
def order_detail(request, order_id: int):
    client = KiotVietClient()
    try:
        raw = client.get_order(order_id)
    except KiotVietAPIError as exc:
        messages.error(request, str(exc))
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
    client = KiotVietClient()
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
        list_fn=client.list_invoices,
        get_by_code_fn=client.get_invoice_by_code,
        format_row_fn=format_invoice_row,
    )


@kiotviet_access_required
def invoice_detail(request, invoice_id: int):
    client = KiotVietClient()
    try:
        raw = client.get_invoice(invoice_id)
    except KiotVietAPIError as exc:
        messages.error(request, str(exc))
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
    extra['retailer'] = KiotVietClient().retailer if KiotVietClient.is_configured() else ''
    return extra
