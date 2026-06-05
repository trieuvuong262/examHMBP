"""Tra cứu hàng hóa, tồn kho, phiếu nhập."""

from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .browse import (
    KV_PAGE_SIZE,
    fetch_api_page,
    get_page_number,
    paginate_api_meta,
    paginate_list_items,
)
from .client import KiotVietAPIError, KiotVietClient
from .decorators import kiotviet_access_required
from . import local_lookup as local
from .mirror import use_local_mirror
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
        'orderBy': 'name',
        'orderDirection': 'Asc',
        'includeInventory': 'true',
    }
    if search_type == 'name' and query:
        params['name'] = query
    return params


def _filter_purchase_by_code(rows: list, query: str) -> list:
    q = query.strip().lower()
    return [r for r in rows if str(r.get('code') or '').lower() == q]


def _filter_products_by_code(rows: list, query: str) -> list:
    q = query.strip().lower()
    return [r for r in rows if str(r.get('code', '')).lower() == q]


@kiotviet_access_required
def product_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'name', 'barcode'):
        search_type = 'code'
    query = get_search_query(request)
    items: list[dict] = []
    total = 0
    api_error = None
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)

    client = KiotVietClient()

    try:
        if use_local_mirror('products'):
            if browse_mode:
                rows, total = local.browse_products(page=page, per_page=KV_PAGE_SIZE)
                items = [format_product_row(r) for r in rows]
            elif search_type == 'code':
                detail = local.get_product_by_code(client.retailer, query)
                if detail:
                    items = [format_product_row(detail)]
                    total = 1
                else:
                    rows, total = local.browse_products(
                        page=page, per_page=KV_PAGE_SIZE, code=query,
                    )
                    items = [format_product_row(r) for r in rows]
            elif search_type == 'barcode':
                rows, total = local.browse_products(
                    page=1, per_page=KV_PAGE_SIZE * 5, bar_code=query,
                )
                all_matched = [format_product_row(r) for r in rows]
                items, page_obj, query_string = paginate_list_items(request, all_matched)
                total = len(all_matched)
            else:
                rows, total = local.browse_products(
                    page=page, per_page=KV_PAGE_SIZE, name=query,
                )
                items = [format_product_row(r) for r in rows]
        elif browse_mode:
            rows, total = fetch_api_page(
                client.list_products,
                _product_list_params('name', ''),
                page,
            )
            items = [format_product_row(r) for r in rows]
        elif search_type == 'code':
            try:
                detail = client.get_product_by_code(query, includeInventory='true')
                items = [format_product_row(detail)]
                total = 1
            except KiotVietAPIError as exc:
                if exc.status_code != 404:
                    raise
                rows, total = fetch_api_page(
                    client.list_products,
                    _product_list_params('name', ''),
                    page,
                )
                filtered = _filter_products_by_code(rows, query)
                if filtered:
                    items = [format_product_row(r) for r in filtered]
                    total = len(items)
                else:
                    items = []
                    total = 0
        elif search_type == 'barcode':
            all_matched: list[dict] = []
            api_total = 0
            for scan_page in range(1, 6):
                rows, api_total = fetch_api_page(
                    client.list_products,
                    {'includeInventory': 'true', 'orderBy': 'name', 'orderDirection': 'Asc'},
                    scan_page,
                )
                for row in rows:
                    if str(row.get('barCode') or '').lower() == query.lower():
                        all_matched.append(format_product_row(row))
                if len(all_matched) >= KV_PAGE_SIZE or scan_page * KV_PAGE_SIZE >= api_total:
                    break
            items, page_obj, query_string = paginate_list_items(request, all_matched)
            total = len(all_matched)
        else:
            rows, total = fetch_api_page(
                client.list_products,
                _product_list_params('name', query),
                page,
            )
            items = [format_product_row(r) for r in rows]
    except KiotVietAPIError as exc:
        api_error = str(exc)
        messages.error(request, api_error)

    if total and page_obj is None and (browse_mode or query):
        page_obj, query_string = paginate_api_meta(request, total)

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
            empty_hint='Nhập mã, tên hoặc mã vạch để lọc. Không nhập từ khóa: xem 30 hàng đầu.',
            type_options=(
                ('code', 'Mã hàng hóa'),
                ('name', 'Tên hàng hóa'),
                ('barcode', 'Mã vạch'),
            ),
            page_obj=page_obj,
            query_string=query_string,
            browse_mode=browse_mode,
            items_count=len(items),
        ),
    )


@kiotviet_access_required
def product_detail(request, product_id: int):
    client = KiotVietClient()
    raw = None
    if use_local_mirror('products'):
        raw = local.get_product(client.retailer, product_id)
    try:
        if raw is None:
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
    total = 0
    api_error = None
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)

    client = KiotVietClient()

    try:
        if use_local_mirror('stock'):
            if browse_mode:
                rows, total = local.browse_stock(page=page, per_page=KV_PAGE_SIZE)
                for product in rows:
                    stock_rows.extend(format_inventory_rows(product))
            elif search_type == 'code':
                rows, total = local.browse_stock(
                    page=1, per_page=KV_PAGE_SIZE, product_code=query,
                )
                for product in rows:
                    stock_rows.extend(format_inventory_rows(product))
                total = len(stock_rows)
            else:
                rows, total = local.browse_stock(
                    page=page, per_page=KV_PAGE_SIZE, product_name=query,
                )
                for product in rows:
                    stock_rows.extend(format_inventory_rows(product))
        elif browse_mode:
            rows, total = fetch_api_page(
                client.list_product_on_hand,
                {'orderBy': 'code', 'orderDirection': 'Asc'},
                page,
            )
            for product in rows:
                stock_rows.extend(format_inventory_rows(product))
        elif search_type == 'code':
            try:
                product = client.get_product_by_code(query, includeInventory='true')
                stock_rows = format_inventory_rows(product)
                total = len(stock_rows)
            except KiotVietAPIError as exc:
                if exc.status_code != 404:
                    raise
                rows, _ = fetch_api_page(
                    client.list_product_on_hand,
                    {'orderBy': 'code', 'orderDirection': 'Asc'},
                    1,
                )
                for row in rows:
                    if str(row.get('code', '')).lower() == query.lower():
                        stock_rows.extend(format_inventory_rows(row))
                total = len(stock_rows)
        else:
            rows, total = fetch_api_page(
                client.list_products,
                _product_list_params('name', query),
                page,
            )
            for product in rows:
                stock_rows.extend(format_inventory_rows(product))
    except KiotVietAPIError as exc:
        api_error = str(exc)
        messages.error(request, api_error)

    if browse_mode or (search_type == 'name' and query):
        if total:
            page_obj, query_string = paginate_api_meta(request, total)

    return render(
        request,
        'kiotviet/stock_lookup.html',
        {
            'search_type': search_type,
            'search_query': query,
            'stock_rows': stock_rows,
            'total': total,
            'api_error': api_error,
            'page_obj': page_obj,
            'query_string': query_string,
            'browse_mode': browse_mode,
            'retailer': client.retailer if KiotVietClient.is_configured() else '',
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
    total = 0
    api_error = None
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)

    client = KiotVietClient()
    list_params = {'orderDirection': 'Desc', 'orderBy': 'purchaseDate'}

    try:
        if use_local_mirror('purchase_orders'):
            if browse_mode:
                rows, total = local.browse_purchase_orders(page=page, per_page=KV_PAGE_SIZE)
                items = [format_purchase_order_row(r) for r in rows]
            elif search_type == 'id' and query.isdigit():
                detail = local.get_purchase_order(client.retailer, int(query))
                if detail:
                    items = [format_purchase_order_row(detail)]
                    total = 1
                else:
                    items = []
                    total = 0
            elif query.isdigit():
                detail = local.get_purchase_order(client.retailer, int(query))
                if detail:
                    items = [format_purchase_order_row(detail)]
                    total = 1
                else:
                    rows, total = local.browse_purchase_orders(
                        page=1, per_page=KV_PAGE_SIZE, code=query,
                    )
                    items = [format_purchase_order_row(r) for r in rows]
                    total = len(items)
            else:
                rows, total = local.browse_purchase_orders(
                    page=1, per_page=KV_PAGE_SIZE * 5, code=query,
                )
                all_matched = [format_purchase_order_row(r) for r in rows]
                items, page_obj, query_string = paginate_list_items(request, all_matched)
                total = len(all_matched)
        elif browse_mode:
            rows, total = fetch_api_page(client.list_purchase_orders, list_params, page)
            items = [format_purchase_order_row(r) for r in rows]
        elif search_type == 'id' and query.isdigit():
            detail = client.get_purchase_order(query)
            items = [format_purchase_order_row(detail)]
            total = 1
        elif query.isdigit():
            try:
                detail = client.get_purchase_order(query)
                items = [format_purchase_order_row(detail)]
                total = 1
            except KiotVietAPIError as exc:
                if exc.status_code != 404:
                    raise
                rows, _ = fetch_api_page(client.list_purchase_orders, list_params, 1)
                matched = _filter_purchase_by_code(rows, query)
                items = [format_purchase_order_row(r) for r in matched]
                total = len(items)
        else:
            all_matched: list[dict] = []
            api_total = 0
            for scan_page in range(1, 6):
                rows, api_total = fetch_api_page(
                    client.list_purchase_orders,
                    list_params,
                    scan_page,
                )
                all_matched.extend(_filter_purchase_by_code(rows, query))
                if all_matched or scan_page * KV_PAGE_SIZE >= api_total:
                    break
            items, page_obj, query_string = paginate_list_items(request, all_matched)
            total = len(all_matched)
    except KiotVietAPIError as exc:
        api_error = str(exc)
        messages.error(request, api_error)

    if total and page_obj is None and (browse_mode or query):
        page_obj, query_string = paginate_api_meta(request, total)

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
            empty_hint='Nhập mã phiếu hoặc ID để lọc. Không nhập từ khóa: xem 30 phiếu mới nhất.',
            type_options=(
                ('code', 'Mã phiếu nhập'),
                ('id', 'ID phiếu'),
            ),
            page_obj=page_obj,
            query_string=query_string,
            browse_mode=browse_mode,
            items_count=len(items),
        ),
    )


@kiotviet_access_required
def purchase_detail(request, purchase_id: int):
    client = KiotVietClient()
    raw = None
    if use_local_mirror('purchase_orders'):
        raw = local.get_purchase_order(client.retailer, purchase_id)
    try:
        if raw is None:
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
