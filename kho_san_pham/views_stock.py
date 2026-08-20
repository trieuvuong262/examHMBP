"""Tồn kho thành phẩm theo hai kho: xưởng vs cửa hàng."""

from decimal import Decimal

from django.db.models import Q
from django.shortcuts import render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_san_pham.models import Product
from kho_san_pham.services.stock import annotate_warehouse_qtys, catalog_and_sales_warehouses
from kho_san_pham.view_utils import nav_context, perm_context

STATUS_CHOICES = (
    ('all', 'Tất cả'),
    ('active', 'Đang dùng'),
    ('inactive', 'Ngừng dùng'),
)

STOCK_ORDER_CHOICES = (
    ('qty_factory:desc', 'Tồn xưởng nhiều → ít'),
    ('qty_factory:asc', 'Tồn xưởng ít → nhiều'),
    ('qty_store:desc', 'Tồn cửa hàng nhiều → ít'),
    ('qty_store:asc', 'Tồn cửa hàng ít → nhiều'),
    ('code:asc', 'SKU A → Z'),
    ('name:asc', 'Tên A → Z'),
)

_SORT_FIELDS = {
    'qty_factory': 'qty_factory',
    'qty_store': 'qty_store',
    'code': 'code',
    'name': 'name',
}

WH_ALL = ''
WH_FACTORY = 'factory'
WH_STORE = 'store'


def _list_status(request) -> str:
    status = (request.GET.get('status') or 'active').strip().lower()
    if status not in {k for k, _ in STATUS_CHOICES}:
        return 'active'
    return status


def _warehouse_scope(request) -> str:
    value = (request.GET.get('wh') or '').strip().lower()
    if value in (WH_FACTORY, WH_STORE):
        return value
    return WH_ALL


def _stock_sort(request):
    order = (request.GET.get('order') or 'qty_factory:desc').strip()
    sort_key, _, sort_dir = order.partition(':')
    sort_key = sort_key.strip()
    sort_dir = sort_dir.strip().lower()
    if sort_key not in _SORT_FIELDS:
        sort_key = 'qty_factory'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc' if sort_key.startswith('qty_') else 'asc'
    return sort_key, sort_dir


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def stock_list(request):
    factory, store = catalog_and_sales_warehouses()
    search_query = get_search_query(request)
    status = _list_status(request)
    wh_scope = _warehouse_scope(request)
    only_stock = (request.GET.get('stock') or '').strip() in ('1', 'yes', 'nonzero')
    sort_key, sort_dir = _stock_sort(request)

    qs = Product.objects.all()
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    if search_query:
        qs = qs.filter(
            Q(code__icontains=search_query)
            | Q(style_code__icontains=search_query)
            | Q(color_code__icontains=search_query)
            | Q(color_label__icontains=search_query)
            | Q(size_label__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(bar_code__icontains=search_query)
        )
    qs = annotate_warehouse_qtys(qs, factory=factory, store=store)
    if only_stock:
        if wh_scope == WH_FACTORY:
            qs = qs.filter(qty_factory__gt=0)
        elif wh_scope == WH_STORE:
            qs = qs.filter(qty_store__gt=0)
        else:
            qs = qs.filter(Q(qty_factory__gt=0) | Q(qty_store__gt=0))

    order = _SORT_FIELDS[sort_key]
    if sort_dir == 'desc':
        order = f'-{order}'
    qs = qs.order_by(order, 'code')

    page_obj, query_string = paginate_queryset(request, qs, per_page=40)
    selected_order = f'{sort_key}:{sort_dir}'
    return render(request, 'kho_san_pham/stock_list.html', {
        **nav_context('stock', user=request.user),
        **perm_context(request.user, 'stock'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': STATUS_CHOICES,
        'wh_scope': wh_scope,
        'wh_choices': (
            (WH_ALL, 'Cả hai kho'),
            (WH_FACTORY, factory.name if factory else 'Xưởng'),
            (WH_STORE, store.name if store else 'Cửa hàng'),
        ),
        'only_stock': only_stock,
        'selected_order': selected_order,
        'order_choices': STOCK_ORDER_CHOICES,
        'factory': factory,
        'store': store,
        'show_factory': wh_scope != WH_STORE,
        'show_store': wh_scope != WH_FACTORY,
        'has_filters': bool(
            search_query
            or status != 'active'
            or wh_scope
            or only_stock
            or selected_order != 'qty_factory:desc'
        ),
    })
