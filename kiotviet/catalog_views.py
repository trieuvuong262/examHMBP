"""Hàng hóa, tồn kho, phiếu nhập — đọc từ mirror kv_*."""

from django.contrib import messages
from django.shortcuts import redirect, render

from PortalJustPlay.list_search import get_search_query

from .browse import KV_PAGE_SIZE, get_page_number, paginate_api_meta, paginate_list_items
from .decorators import kiotviet_access_required
from . import local_lookup as local
from .formatters import (
    format_inventory_rows,
    format_product_group_detail,
    format_product_group_row,
    format_purchase_order_detail,
    format_purchase_order_row,
)
from .product_filters import (
    PRODUCT_TYPE_OPTIONS,
    SORT_OPTIONS,
    list_category_filter_options,
    list_unit_filter_options,
    parse_product_filters,
)
from .product_groups import browse_product_groups, get_product_group
from .lookup_views import _lookup_context
from .sync_service import current_retailer
from .views import MIRROR_EMPTY_HINT


@kiotviet_access_required
def product_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'name', 'barcode'):
        search_type = 'code'
    query = get_search_query(request)
    list_filters = parse_product_filters(request)
    items: list[dict] = []
    total = 0
    page_obj = None
    query_string = ''
    has_active_filters = list_filters.is_non_default_filter()
    browse_mode = not query and not has_active_filters
    page = get_page_number(request)
    retailer = current_retailer()
    browse_kwargs = {
        'page': page,
        'per_page': KV_PAGE_SIZE,
        'retailer': retailer,
        'filters': list_filters,
    }

    if search_type == 'barcode' and query:
        groups, total = browse_product_groups(
            page=1, per_page=KV_PAGE_SIZE * 50, bar_code=query, **browse_kwargs,
        )
        all_matched = [format_product_group_row(g) for g in groups]
        items, page_obj, query_string = paginate_list_items(request, all_matched)
        total = len(all_matched)
    else:
        search_kwargs = {}
        if query:
            if search_type == 'code':
                search_kwargs['code'] = query
            else:
                search_kwargs['name'] = query
        groups, total = browse_product_groups(**browse_kwargs, **search_kwargs)
        items = [format_product_group_row(g) for g in groups]

    if total and page_obj is None and (browse_mode or query or has_active_filters):
        page_obj, query_string = paginate_api_meta(request, total)

    return render(
        request,
        'kiotviet/product_lookup.html',
        _lookup_context(
            request,
            title='Hàng hoá',
            icon='bi-box-seam',
            search_type=search_type,
            search_query=query,
            items=items,
            total=total,
            api_error=None,
            mirror_empty_hint=MIRROR_EMPTY_HINT if total == 0 else '',
            detail_url_name='kiotviet:product_detail',
            empty_hint='Mặc định chỉ hàng đang kinh doanh. Dùng bộ lọc hoặc từ khóa để thu hẹp danh sách.',
            product_group_mode=True,
            product_filters=list_filters,
            category_options=list_category_filter_options(retailer),
            unit_options=list_unit_filter_options(retailer),
            product_type_options=PRODUCT_TYPE_OPTIONS,
            sort_options=SORT_OPTIONS,
            has_active_filters=has_active_filters,
            default_active_only=True,
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
    retailer = current_retailer()
    raw = get_product_group(retailer, product_id)
    if raw is None:
        messages.error(request, 'Không tìm thấy hàng hóa trong dữ liệu đã sync.')
        return redirect('kiotviet:product_lookup')
    return render(
        request,
        'kiotviet/product_detail.html',
        {'product': format_product_group_detail(raw)},
    )


@kiotviet_access_required
def stock_lookup(request):
    search_type = (request.GET.get('type') or 'code').strip()
    if search_type not in ('code', 'name'):
        search_type = 'code'
    query = get_search_query(request)
    stock_rows: list[dict] = []
    total = 0
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)
    retailer = current_retailer()

    if browse_mode:
        rows, total = local.browse_stock(page=page, per_page=KV_PAGE_SIZE, retailer=retailer)
        for product in rows:
            stock_rows.extend(format_inventory_rows(product))
    elif search_type == 'code':
        rows, total = local.browse_stock(
            page=1, per_page=KV_PAGE_SIZE, product_code=query, retailer=retailer,
        )
        for product in rows:
            stock_rows.extend(format_inventory_rows(product))
        total = len(stock_rows)
    else:
        rows, total = local.browse_stock(
            page=page, per_page=KV_PAGE_SIZE, product_name=query, retailer=retailer,
        )
        for product in rows:
            stock_rows.extend(format_inventory_rows(product))

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
            'api_error': None,
            'mirror_empty_hint': MIRROR_EMPTY_HINT if not stock_rows else '',
            'page_obj': page_obj,
            'query_string': query_string,
            'browse_mode': browse_mode,
            'retailer': retailer,
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
    page_obj = None
    query_string = ''
    browse_mode = not query
    page = get_page_number(request)
    retailer = current_retailer()

    if browse_mode:
        rows, total = local.browse_purchase_orders(page=page, per_page=KV_PAGE_SIZE, retailer=retailer)
        items = [format_purchase_order_row(r) for r in rows]
    elif search_type == 'id' and query.isdigit():
        detail = local.get_purchase_order(retailer, int(query))
        if detail:
            items = [format_purchase_order_row(detail)]
            total = 1
        else:
            items = []
            total = 0
    elif query.isdigit():
        detail = local.get_purchase_order(retailer, int(query))
        if detail:
            items = [format_purchase_order_row(detail)]
            total = 1
        else:
            rows, total = local.browse_purchase_orders(
                page=1, per_page=KV_PAGE_SIZE, code=query, retailer=retailer,
            )
            items = [format_purchase_order_row(r) for r in rows]
            total = len(items)
    else:
        rows, total = local.browse_purchase_orders(
            page=1, per_page=KV_PAGE_SIZE * 5, code=query, retailer=retailer,
        )
        all_matched = [format_purchase_order_row(r) for r in rows]
        items, page_obj, query_string = paginate_list_items(request, all_matched)
        total = len(all_matched)

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
            api_error=None,
            mirror_empty_hint=MIRROR_EMPTY_HINT if total == 0 else '',
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
    retailer = current_retailer()
    raw = local.get_purchase_order(retailer, purchase_id)
    if raw is None:
        messages.error(request, 'Không tìm thấy phiếu nhập trong dữ liệu đã sync.')
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
