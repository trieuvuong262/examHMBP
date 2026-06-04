"""Tra cứu đơn đặt hàng & hóa đơn — logic dùng chung."""

from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

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
        'pageSize': 50,
        'currentItem': 0,
        'orderDirection': 'Desc',
    }
    if search_type == 'customer_code':
        params['customerCode'] = query
        params['orderBy'] = 'purchaseDate'
    else:
        params['orderBy'] = 'purchaseDate'
    return params


@kiotviet_access_required
def order_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'customer_code'):
        search_type = 'code'
    query = get_search_query(request)
    items: list[dict] = []
    total = None
    api_error = None

    if query:
        client = KiotVietClient()
        try:
            if search_type == 'code':
                try:
                    detail = client.get_order_by_code(query)
                    items = [format_order_row(detail)]
                    total = 1
                except KiotVietAPIError as exc:
                    if exc.status_code != 404:
                        raise
                    payload = client.list_orders(**_list_params('code', query))
                    rows = payload.get('data') or []
                    items = [format_order_row(r) for r in rows]
                    total = payload.get('total', len(items))
            else:
                payload = client.list_orders(**_list_params(search_type, query))
                rows = payload.get('data') or []
                items = [format_order_row(r) for r in rows]
                total = payload.get('total', len(items))
        except KiotVietAPIError as exc:
            api_error = str(exc)
            messages.error(request, api_error)

    return render(
        request,
        'kiotviet/order_lookup.html',
        _lookup_context(
            request,
            title='Tra cứu đơn đặt hàng',
            icon='bi-cart-check',
            search_type=search_type,
            search_query=query,
            items=items,
            total=total,
            api_error=api_error,
            detail_url_name='kiotviet:order_detail',
            empty_hint='Nhập mã đơn hoặc mã khách hàng để tra cứu đơn đặt hàng.',
            type_options=(
                ('code', 'Mã đơn đặt hàng'),
                ('customer_code', 'Mã khách hàng'),
            ),
        ),
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
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'customer_code'):
        search_type = 'code'
    query = get_search_query(request)
    items: list[dict] = []
    total = None
    api_error = None

    if query:
        client = KiotVietClient()
        try:
            if search_type == 'code':
                try:
                    detail = client.get_invoice_by_code(query)
                    items = [format_invoice_row(detail)]
                    total = 1
                except KiotVietAPIError as exc:
                    if exc.status_code != 404:
                        raise
                    payload = client.list_invoices(**_list_params('code', query))
                    rows = payload.get('data') or []
                    items = [format_invoice_row(r) for r in rows]
                    total = payload.get('total', len(items))
            else:
                payload = client.list_invoices(**_list_params(search_type, query))
                rows = payload.get('data') or []
                items = [format_invoice_row(r) for r in rows]
                total = payload.get('total', len(items))
        except KiotVietAPIError as exc:
            api_error = str(exc)
            messages.error(request, api_error)

    return render(
        request,
        'kiotviet/invoice_lookup.html',
        _lookup_context(
            request,
            title='Tra cứu hóa đơn',
            icon='bi-receipt',
            search_type=search_type,
            search_query=query,
            items=items,
            total=total,
            api_error=api_error,
            detail_url_name='kiotviet:invoice_detail',
            empty_hint='Nhập mã hóa đơn hoặc mã khách hàng để tra cứu.',
            type_options=(
                ('code', 'Mã hóa đơn'),
                ('customer_code', 'Mã khách hàng'),
            ),
        ),
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
