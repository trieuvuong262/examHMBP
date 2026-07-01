import json
from datetime import date

import pandas as pd
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import (
    STOCK_STATUS_LABELS,
    STOCK_STATUS_LOW,
    STOCK_STATUS_OK,
    STOCK_STATUS_OUT,
)
from kho_npl.category_tree import active_category_roots, category_cascade_for_filter, category_children_for_parent
from kho_npl.filter_utils import append_filter_params, parse_int_ids
from kho_npl.models import Material, MaterialCategory, WarehouseLocation
from kho_npl.overview_list_columns import (
    OVERVIEW_LIST_COLUMNS,
    OVERVIEW_LIST_SORT_FIELDS,
    OVERVIEW_LIST_TOTAL_COL_WEIGHT,
)
from kho_npl.stock_card_catalog_columns import (
    STOCK_CARD_CATALOG_COLUMNS,
    STOCK_CARD_CATALOG_SORT_FIELDS,
    STOCK_CARD_CATALOG_TOTAL_COL_WEIGHT,
)
from kho_npl.services.excel_export import dataframe_to_xlsx_response
from kho_npl.services.scrap_warehouse import filter_storage_location_ids, source_locations_qs
from kho_npl.services.stock import material_stock_rows, overview_stats, stock_rows_for_status
from kho_npl.services.stock_card import build_material_stock_card, diagnose_stock_mismatch
from kho_npl.view_utils import nav_context, perm_context
from kho_npl.views_material import _material_catalog_qs
from kho_npl.views_settings import settings_hub_items

STOCK_ALERT_STATUS_CHOICES = {
    STOCK_STATUS_LOW: {
        'title': 'NPL sắp thiếu',
        'icon': 'bi-exclamation-triangle',
        'badge': 'warning',
    },
    STOCK_STATUS_OUT: {
        'title': 'NPL hết hàng',
        'icon': 'bi-x-octagon',
        'badge': 'danger',
    },
}


def _filter_alert_rows(rows, search_query: str):
    if not search_query:
        return rows
    q = search_query.lower()
    return [
        r for r in rows
        if q in r['material'].code.lower()
        or q in r['material'].name.lower()
        or q in (r['material'].color.name if r['material'].color_id else '').lower()
    ]


OVERVIEW_STOCK_STATUS_CHOICES = (
    ('', 'Tất cả'),
    (STOCK_STATUS_OK, 'Đủ hàng'),
    (STOCK_STATUS_LOW, 'Sắp thiếu'),
    (STOCK_STATUS_OUT, 'Hết hàng'),
)


def _overview_sort(request):
    sort_key = (request.GET.get('sort') or 'code').strip()
    sort_dir = (request.GET.get('dir') or 'asc').strip().lower()
    if sort_key not in OVERVIEW_LIST_SORT_FIELDS:
        sort_key = 'code'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    return sort_key, sort_dir


def _overview_filtered_rows(request):
    search_query = get_search_query(request)
    category_ids = parse_int_ids(request, 'category')
    status = (request.GET.get('status') or '').strip().lower()
    if status not in (STOCK_STATUS_OK, STOCK_STATUS_LOW, STOCK_STATUS_OUT):
        status = ''

    qs = Material.objects.filter(is_active=True).select_related(
        'category', 'unit', 'supplier', 'color', 'specification',
    )
    if category_ids:
        qs = qs.filter(category_id__in=category_ids)
    if search_query:
        qs = qs.filter(
            Q(code__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(color__name__icontains=search_query)
            | Q(specification__name__icontains=search_query),
        )

    rows = material_stock_rows(qs)
    if status:
        rows = [r for r in rows if r['status'] == status]

    sort_key, sort_dir = _overview_sort(request)
    sort_fn = OVERVIEW_LIST_SORT_FIELDS[sort_key]
    rows.sort(key=sort_fn, reverse=(sort_dir == 'desc'))
    return rows, search_query, category_ids, status, sort_key, sort_dir


@module_perm_required(MODULE_KHO_NPL, 'view')
def overview(request):
    rows, search_query, category_ids, status, sort_key, sort_dir = _overview_filtered_rows(request)
    stats = overview_stats()
    page_obj, query_string = paginate_queryset(request, rows, per_page=25)
    mat_perms = perm_context(request.user, 'materials')
    return render(request, 'kho_npl/overview.html', {
        **nav_context('overview', user=request.user),
        **perm_context(request.user, 'overview'),
        'can_create': mat_perms.get('can_create', False),
        'stats': stats,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'categories': MaterialCategory.objects.filter(is_active=True),
        'selected_categories': category_ids,
        'selected_status': status,
        'status_choices': OVERVIEW_STOCK_STATUS_CHOICES,
        'list_columns': OVERVIEW_LIST_COLUMNS,
        'total_col_weight': OVERVIEW_LIST_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'has_filters': bool(search_query or category_ids or status),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def overview_export(request):
    rows, _, _, _, _, _ = _overview_filtered_rows(request)
    data = []
    for row in rows:
        mat = row['material']
        data.append({
            'Mã NPL': mat.code,
            'Tên NPL': mat.name,
            'Nhóm': mat.category.name,
            'Màu': mat.color.name if mat.color_id else '',
            'ĐVT': mat.unit.name,
            'Tồn': float(row['total_qty']),
            'Tối thiểu': float(mat.min_stock),
            'Vị trí': row['primary_location'],
            'Trạng thái': STOCK_STATUS_LABELS[row['status']],
        })
    df = pd.DataFrame(data)
    return dataframe_to_xlsx_response(df, 'Tong_quan_ton_kho', 'Tong_quan')


def _parse_optional_date(value: str) -> date | None:
    value = (value or '').strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _stock_card_catalog_sort(request):
    sort_key = (request.GET.get('sort') or 'code').strip()
    sort_dir = (request.GET.get('dir') or 'asc').strip().lower()
    if sort_key not in STOCK_CARD_CATALOG_SORT_FIELDS:
        sort_key = 'code'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    orm_field = STOCK_CARD_CATALOG_SORT_FIELDS[sort_key]
    order = orm_field if sort_dir == 'asc' else f'-{orm_field}'
    return sort_key, sort_dir, order


def _stock_card_catalog_qs(request):
    catalog_qs, search_query, category_ids, category_parent_id, _ = _material_catalog_qs(request)
    sort_key, sort_dir, order = _stock_card_catalog_sort(request)
    catalog_qs = catalog_qs.order_by(order)
    return catalog_qs, search_query, category_ids, category_parent_id, sort_key, sort_dir


def _stock_card_sort_filter_params(sort_key, sort_dir):
    params = []
    if sort_key and sort_key != 'code':
        params.append(f'sort={sort_key}')
    if sort_dir and sort_dir != 'asc':
        params.append(f'dir={sort_dir}')
    return params


def _stock_card_card_filter_qs(
    *,
    date_from,
    date_to,
    location_ids,
    sort_key,
    sort_dir,
    show_diagnosis=False,
):
    filter_params = []
    if date_from:
        filter_params.append(f'date_from={date_from.isoformat()}')
    if date_to:
        filter_params.append(f'date_to={date_to.isoformat()}')
    append_filter_params(filter_params, locations=location_ids)
    filter_params.extend(_stock_card_sort_filter_params(sort_key, sort_dir))
    if show_diagnosis:
        filter_params.append('diagnose=1')
    return '&'.join(filter_params)


def _stock_card_catalog_only_filter_qs(
    *,
    category_ids,
    category_parent_id,
    search_query,
    sort_key,
    sort_dir,
    show_diagnosis=False,
):
    filter_params = []
    append_filter_params(
        filter_params,
        categories=category_ids,
        category_parent=category_parent_id,
    )
    if search_query:
        filter_params.append(f'q={search_query}')
    filter_params.extend(_stock_card_sort_filter_params(sort_key, sort_dir))
    if show_diagnosis:
        filter_params.append('diagnose=1')
    return '&'.join(filter_params)


def _stock_card_catalog_filter_qs(
    *,
    date_from,
    date_to,
    location_ids,
    category_ids,
    category_parent_id,
    search_query,
    sort_key,
    sort_dir,
    show_diagnosis=False,
):
    filter_params = []
    if date_from:
        filter_params.append(f'date_from={date_from.isoformat()}')
    if date_to:
        filter_params.append(f'date_to={date_to.isoformat()}')
    append_filter_params(
        filter_params,
        locations=location_ids,
        categories=category_ids,
        category_parent=category_parent_id,
    )
    if search_query:
        filter_params.append(f'q={search_query}')
    filter_params.extend(_stock_card_sort_filter_params(sort_key, sort_dir))
    if show_diagnosis:
        filter_params.append('diagnose=1')
    return '&'.join(filter_params)


@module_perm_required(MODULE_KHO_NPL, 'view')
def stock_cards(request):
    if request.GET.get('page') and not request.GET.get('cat_page'):
        params = request.GET.copy()
        params['cat_page'] = params['page']
        del params['page']
        return redirect(f'{request.path}?{params.urlencode()}')

    location_ids = filter_storage_location_ids(parse_int_ids(request, 'location'))
    material_id = request.GET.get('material', '').strip()
    date_from = _parse_optional_date(request.GET.get('date_from'))
    date_to = _parse_optional_date(request.GET.get('date_to'))
    show_diagnosis = request.GET.get('diagnose') == '1'

    catalog_qs, search_query, category_ids, category_parent_id, sort_key, sort_dir = _stock_card_catalog_qs(request)
    catalog_page, catalog_query_string = paginate_queryset(
        request, catalog_qs, per_page=4, page_param='cat_page',
    )

    selected_material = None
    card = None
    mismatch_diagnosis = None
    if material_id.isdigit():
        selected_material = get_object_or_404(
            Material.objects.select_related('category', 'unit'),
            pk=int(material_id),
        )
        card_kwargs = {'date_from': date_from, 'date_to': date_to}
        if len(location_ids) == 1:
            card_kwargs['location_id'] = location_ids[0]
        elif location_ids:
            card_kwargs['location_ids'] = location_ids
        card = build_material_stock_card(selected_material, **card_kwargs)
        if card and not card['is_consistent']:
            mismatch_diagnosis = diagnose_stock_mismatch(selected_material)

    card_filter_qs = _stock_card_card_filter_qs(
        date_from=date_from,
        date_to=date_to,
        location_ids=location_ids,
        sort_key=sort_key,
        sort_dir=sort_dir,
        show_diagnosis=show_diagnosis,
    )
    catalog_only_filter_qs = _stock_card_catalog_only_filter_qs(
        category_ids=category_ids,
        category_parent_id=category_parent_id,
        search_query=search_query,
        sort_key=sort_key,
        sort_dir=sort_dir,
        show_diagnosis=show_diagnosis,
    )
    catalog_filter_qs = _stock_card_catalog_filter_qs(
        date_from=date_from,
        date_to=date_to,
        location_ids=location_ids,
        category_ids=category_ids,
        category_parent_id=category_parent_id,
        search_query=search_query,
        sort_key=sort_key,
        sort_dir=sort_dir,
        show_diagnosis=show_diagnosis,
    )
    catalog_clear_qs = _stock_card_card_filter_qs(
        date_from=date_from,
        date_to=date_to,
        location_ids=location_ids,
        sort_key=sort_key,
        sort_dir=sort_dir,
        show_diagnosis=show_diagnosis,
    )
    has_card_filters = bool(date_from or date_to or location_ids)
    has_catalog_filters = bool(search_query or category_ids or category_parent_id)
    has_filters = has_card_filters or has_catalog_filters

    return render(request, 'kho_npl/stock_cards.html', {
        **nav_context('stock_cards', user=request.user),
        **perm_context(request.user, 'stock_cards'),
        'search_query': search_query,
        'locations': source_locations_qs(),
        'category_roots': active_category_roots(),
        'category_children': category_children_for_parent(category_parent_id),
        'category_cascade_json': json.dumps(category_cascade_for_filter()),
        'selected_locations': location_ids,
        'selected_categories': category_ids,
        'selected_category_parent': category_parent_id,
        'selected_material': selected_material,
        'card': card,
        'mismatch_diagnosis': mismatch_diagnosis,
        'show_diagnosis': show_diagnosis,
        'date_from': date_from,
        'date_to': date_to,
        'catalog_page': catalog_page,
        'catalog_query_string': catalog_query_string,
        'catalog_select_base': request.path,
        'catalog_filter_qs': catalog_filter_qs,
        'card_filter_qs': card_filter_qs,
        'catalog_only_filter_qs': catalog_only_filter_qs,
        'catalog_clear_qs': catalog_clear_qs,
        'list_columns': STOCK_CARD_CATALOG_COLUMNS,
        'total_col_weight': STOCK_CARD_CATALOG_TOTAL_COL_WEIGHT,
        'sort_key': sort_key,
        'sort_dir': sort_dir,
        'has_filters': has_filters,
        'has_card_filters': has_card_filters,
        'has_catalog_filters': has_catalog_filters,
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def stock_alerts(request):
    status = (request.GET.get('status') or '').strip().lower()
    if status not in STOCK_ALERT_STATUS_CHOICES:
        status = ''

    search_query = get_search_query(request)
    rows = stock_rows_for_status(material_stock_rows(), status or None)
    rows = _filter_alert_rows(rows, search_query)
    page_obj, query_string = paginate_queryset(request, rows, per_page=25)

    if status:
        meta = STOCK_ALERT_STATUS_CHOICES[status]
        page_title = meta['title']
        page_icon = meta['icon']
    else:
        page_title = 'Cảnh báo tồn kho'
        page_icon = 'bi-exclamation-triangle'

    return render(request, 'kho_npl/stock_alerts.html', {
        **nav_context('overview', user=request.user),
        **perm_context(request.user, 'overview'),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': STOCK_ALERT_STATUS_CHOICES,
        'page_title': page_title,
        'page_icon': page_icon,
        'total_count': len(rows),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def settings_hub(request):
    return render(request, 'kho_npl/settings_hub.html', {
        **nav_context('settings', user=request.user),
        **perm_context(request.user, 'settings'),
        'settings_items': settings_hub_items(),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def hub_redirect(request):
    return redirect('kho_npl:overview')
