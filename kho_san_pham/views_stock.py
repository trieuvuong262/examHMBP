"""Tồn kho thành phẩm — gom theo Style như danh mục SKU, số theo chi nhánh KiotViet."""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_san_pham.models import Product
from kho_san_pham.services.stock import catalog_and_sales_warehouses
from kho_san_pham.services.style_groups import format_style_group, group_products_by_style
from kho_san_pham.services.sync_store_stock import (
    attach_kv_branch_qtys,
    kv_inventory_branch_groups,
)
from kho_san_pham.sku_vocabulary import extract_sp_number
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
    ('code:desc', 'Số SP lớn → nhỏ'),
    ('code:asc', 'Số SP nhỏ → lớn'),
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
        sort_dir = 'desc' if sort_key.startswith('qty_') or sort_key == 'code' else 'asc'
    return sort_key, sort_dir


def _column_index(columns: list[dict]) -> dict[int, int]:
    return {col['id']: i for i, col in enumerate(columns)}


def _qtys_for(product, columns: list[dict], index: dict[int, int]) -> list[Decimal]:
    source = getattr(product, 'kv_branch_qtys', None) or []
    out: list[Decimal] = []
    for col in columns:
        pos = index.get(col['id'])
        if pos is None or pos >= len(source):
            out.append(Decimal('0'))
        else:
            out.append(source[pos] or Decimal('0'))
    return out


def _sum_qtys(qtys: list[Decimal]) -> Decimal:
    return sum(qtys, Decimal('0'))


def _format_stock_group(group, product_map: dict, all_columns: list[dict], display_columns: list[dict]) -> dict:
    data = format_style_group(group)
    index = _column_index(all_columns)
    factory_cols = [c for c in display_columns if c['group'] == WH_FACTORY]
    store_cols = [c for c in display_columns if c['group'] == WH_STORE]
    group_totals = [Decimal('0')] * len(display_columns)
    variants = []
    for variant in data['variants']:
        product = product_map.get(variant['id'])
        qtys = _qtys_for(product, display_columns, index) if product else [Decimal('0')] * len(display_columns)
        variant['kv_branch_qtys_pairs'] = list(zip(display_columns, qtys, strict=True))
        variant['qty_factory'] = _sum_qtys(_qtys_for(product, factory_cols, index) if product else [])
        variant['qty_store'] = _sum_qtys(_qtys_for(product, store_cols, index) if product else [])
        for i, qty in enumerate(qtys):
            group_totals[i] += qty
        variants.append(variant)
    data['variants'] = variants
    data['kv_branch_qtys_pairs'] = list(zip(display_columns, group_totals, strict=True))
    data['qty_factory'] = _sum_qtys([q for c, q in data['kv_branch_qtys_pairs'] if c['group'] == WH_FACTORY])
    data['qty_store'] = _sum_qtys([q for c, q in data['kv_branch_qtys_pairs'] if c['group'] == WH_STORE])
    return data


def _group_code_sort_key(item: dict) -> tuple:
    text = (item.get('style_code') or '').strip()
    if not text or text == '—':
        text = item.get('code') or ''
    return (extract_sp_number(text), text.upper())


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def stock_list(request):
    factory, store = catalog_and_sales_warehouses()
    search_query = get_search_query(request)
    status = _list_status(request)
    wh_scope = _warehouse_scope(request)
    only_stock = (request.GET.get('stock') or '').strip() in ('1', 'yes', 'nonzero')
    sort_key, sort_dir = _stock_sort(request)

    groups_kv = kv_inventory_branch_groups()
    factory_cols = [
        {'id': bid, 'name': name, 'group': WH_FACTORY}
        for bid, name in groups_kv['factory']
    ]
    store_cols = [
        {'id': bid, 'name': name, 'group': WH_STORE}
        for bid, name in groups_kv['sales']
    ]
    all_columns = factory_cols + store_cols
    if wh_scope == WH_FACTORY:
        kv_columns = factory_cols
    elif wh_scope == WH_STORE:
        kv_columns = store_cols
    else:
        kv_columns = all_columns

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
    qs = qs.order_by('style_code', 'color_code', 'size_label', 'code')

    products = list(qs)
    attach_kv_branch_qtys(products, all_columns)
    product_map = {p.pk: p for p in products}
    rows = [
        _format_stock_group(group, product_map, all_columns, kv_columns)
        for group in group_products_by_style(products)
    ]

    if only_stock:
        if wh_scope == WH_FACTORY:
            rows = [row for row in rows if (row.get('qty_factory') or 0) > 0]
        elif wh_scope == WH_STORE:
            rows = [row for row in rows if (row.get('qty_store') or 0) > 0]
        else:
            rows = [
                row for row in rows
                if (row.get('qty_factory') or 0) > 0 or (row.get('qty_store') or 0) > 0
            ]

    reverse = sort_dir == 'desc'
    if sort_key == 'code':
        rows.sort(key=_group_code_sort_key, reverse=reverse)
    elif sort_key == 'name':
        rows.sort(key=lambda row: (row.get('name') or '').casefold(), reverse=reverse)
    else:
        rows.sort(key=lambda row: row.get(sort_key) or 0, reverse=reverse)

    page_obj, query_string = paginate_queryset(request, rows, per_page=40)
    selected_order = f'{sort_key}:{sort_dir}'
    factory_label = 'Xưởng (KV)'
    store_label = 'Cửa hàng (KV)'
    if factory_cols:
        factory_label = factory_cols[0]['name'] if len(factory_cols) == 1 else 'Xưởng (KV)'
    if store_cols:
        store_label = store_cols[0]['name'] if len(store_cols) == 1 else 'Cửa hàng (KV)'
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
            (WH_ALL, 'Tất cả kho KV'),
            (WH_FACTORY, factory_label),
            (WH_STORE, store_label),
        ),
        'only_stock': only_stock,
        'selected_order': selected_order,
        'order_choices': STOCK_ORDER_CHOICES,
        'factory': factory,
        'store': store,
        'kv_columns': kv_columns,
        'expand_search_hits': bool(search_query),
        'has_filters': bool(
            search_query
            or status != 'active'
            or wh_scope
            or only_stock
            or selected_order != 'qty_factory:desc'
        ),
    })


@module_perm_required(MODULE_KHO_SAN_PHAM, 'update')
@require_POST
def stock_sync_kv(request):
    from kho_san_pham.services.sync_store_stock import sync_store_stock_from_kiotviet

    result = sync_store_stock_from_kiotviet(apply=True, user=request.user)
    if result.errors and not result.applied:
        messages.error(request, result.errors[0])
    else:
        msg = result.summary() + '.'
        if result.errors:
            messages.warning(request, msg + f' ({len(result.errors)} lỗi)')
        else:
            messages.success(request, msg)
    return redirect('kho_san_pham:stock_list')
