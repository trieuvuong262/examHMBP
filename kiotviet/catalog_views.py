"""Tra cứu hàng hóa, tồn kho, phiếu nhập."""

from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .client import KiotVietAPIError, KiotVietClient
from .decorators import kiotviet_access_required
from .formatters import (
    format_inventory_rows,
    format_product_detail,
    format_product_row,
    format_purchase_order_detail,
    format_purchase_order_row,
)
from .lookup_views import _lookup_context


def _product_list_params(search_type: str, query: str) -> dict:
    params = {
        'pageSize': 50,
        'currentItem': 0,
        'orderBy': 'name',
        'orderDirection': 'Asc',
        'includeInventory': 'true',
    }
    if search_type == 'name':
        params['name'] = query
    return params


def _filter_purchase_by_code(rows: list, query: str) -> list:
    q = query.strip().lower()
    return [r for r in rows if str(r.get('code') or '').lower() == q]


@kiotviet_access_required
def product_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'name', 'barcode'):
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
                    detail = client.get_product_by_code(
                        query,
                        includeInventory='true',
                    )
                    items = [format_product_row(detail)]
                    total = 1
                except KiotVietAPIError as exc:
                    if exc.status_code != 404:
                        raise
                    payload = client.list_products(**_product_list_params('code', query))
                    rows = payload.get('data') or []
                    items = [format_product_row(r) for r in rows if str(r.get('code', '')).lower() == query.lower()]
                    total = len(items)
            elif search_type == 'barcode':
                payload = client.list_products(pageSize=100, currentItem=0, includeInventory='true')
                rows = payload.get('data') or []
                items = [
                    format_product_row(r)
                    for r in rows
                    if str(r.get('barCode') or '').lower() == query.lower()
                ]
                total = len(items)
            else:
                payload = client.list_products(**_product_list_params('name', query))
                rows = payload.get('data') or []
                items = [format_product_row(r) for r in rows]
                total = payload.get('total', len(items))
        except KiotVietAPIError as exc:
            api_error = str(exc)
            messages.error(request, api_error)

    return render(
        request,
        'kiotviet/product_lookup.html',
        _lookup_context(
            request,
            title='Tra cứu hàng hóa',
            icon='bi-box-seam',
            search_type=search_type,
            search_query=query,
            items=items,
            total=total,
            api_error=api_error,
            detail_url_name='kiotviet:product_detail',
            empty_hint='Nhập mã hàng, tên hoặc mã vạch để tra cứu sản phẩm.',
            type_options=(
                ('code', 'Mã hàng hóa'),
                ('name', 'Tên hàng hóa'),
                ('barcode', 'Mã vạch'),
            ),
        ),
    )


@kiotviet_access_required
def product_detail(request, product_id: int):
    client = KiotVietClient()
    try:
        raw = client.get_product(product_id, includeInventory='true')
    except KiotVietAPIError as exc:
        messages.error(request, str(exc))
        return redirect('kiotviet:product_lookup')
    return render(
        request,
        'kiotviet/product_detail.html',
        {'product': format_product_detail(raw)},
    )


@kiotviet_access_required
def stock_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'name'):
        search_type = 'code'
    query = get_search_query(request)
    stock_rows: list[dict] = []
    total = None
    api_error = None

    if query:
        client = KiotVietClient()
        try:
            products: list[dict] = []
            if search_type == 'code':
                try:
                    products = [client.get_product_by_code(query, includeInventory='true')]
                except KiotVietAPIError as exc:
                    if exc.status_code != 404:
                        raise
                    payload = client.list_product_on_hand(
                        pageSize=100,
                        currentItem=0,
                        orderBy='code',
                    )
                    for row in payload.get('data') or []:
                        if str(row.get('code', '')).lower() == query.lower():
                            products.append(row)
            else:
                payload = client.list_products(**_product_list_params('name', query))
                products = payload.get('data') or []

            for product in products:
                stock_rows.extend(format_inventory_rows(product))

            if not stock_rows and search_type == 'code':
                payload = client.list_product_on_hand(pageSize=100, currentItem=0)
                for row in payload.get('data') or []:
                    if str(row.get('code', '')).lower() == query.lower():
                        stock_rows.extend(format_inventory_rows(row))

            total = len(stock_rows)
        except KiotVietAPIError as exc:
            api_error = str(exc)
            messages.error(request, api_error)

    return render(
        request,
        'kiotviet/stock_lookup.html',
        {
            'search_type': search_type,
            'search_query': query,
            'stock_rows': stock_rows,
            'total': total,
            'api_error': api_error,
            'retailer': KiotVietClient().retailer if KiotVietClient.is_configured() else '',
            'type_options': (
                ('code', 'Mã hàng hóa'),
                ('name', 'Tên hàng hóa'),
            ),
        },
    )


@kiotviet_access_required
def purchase_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'id'):
        search_type = 'code'
    query = get_search_query(request)
    items: list[dict] = []
    total = None
    api_error = None

    if query:
        client = KiotVietClient()
        try:
            if search_type == 'id' and query.isdigit():
                detail = client.get_purchase_order(query)
                items = [format_purchase_order_row(detail)]
                total = 1
            else:
                if query.isdigit():
                    try:
                        detail = client.get_purchase_order(query)
                        items = [format_purchase_order_row(detail)]
                        total = 1
                    except KiotVietAPIError as exc:
                        if exc.status_code != 404:
                            raise
                        payload = client.list_purchase_orders(
                            pageSize=100,
                            currentItem=0,
                            orderDirection='Desc',
                        )
                        rows = _filter_purchase_by_code(payload.get('data') or [], query)
                        items = [format_purchase_order_row(r) for r in rows]
                        total = len(items)
                else:
                    payload = client.list_purchase_orders(
                        pageSize=100,
                        currentItem=0,
                        orderDirection='Desc',
                    )
                    rows = _filter_purchase_by_code(payload.get('data') or [], query)
                    items = [format_purchase_order_row(r) for r in rows]
                    total = len(items)
        except KiotVietAPIError as exc:
            api_error = str(exc)
            messages.error(request, api_error)

    return render(
        request,
        'kiotviet/purchase_lookup.html',
        _lookup_context(
            request,
            title='Tra cứu phiếu nhập',
            icon='bi-box-arrow-in-down',
            search_type=search_type,
            search_query=query,
            items=items,
            total=total,
            api_error=api_error,
            detail_url_name='kiotviet:purchase_detail',
            empty_hint='Nhập mã phiếu nhập hoặc ID phiếu để tra cứu.',
            type_options=(
                ('code', 'Mã phiếu nhập'),
                ('id', 'ID phiếu'),
            ),
        ),
    )


@kiotviet_access_required
def purchase_detail(request, purchase_id: int):
    client = KiotVietClient()
    try:
        raw = client.get_purchase_order(purchase_id)
    except KiotVietAPIError as exc:
        messages.error(request, str(exc))
        return redirect('kiotviet:purchase_lookup')
    return render(
        request,
        'kiotviet/_purchase_detail.html',
        {
            'doc': format_purchase_order_detail(raw),
            'header_icon': 'bi-box-arrow-in-down',
            'back_url_name': 'kiotviet:purchase_lookup',
        },
    )
