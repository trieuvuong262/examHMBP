from datetime import date

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import STOCK_STATUS_LOW, STOCK_STATUS_OK, STOCK_STATUS_OUT
from kho_npl.models import Material, MaterialCategory, WarehouseLocation
from kho_npl.services.stock import material_stock_rows, overview_stats, stock_rows_for_status
from kho_npl.services.stock_card import build_material_stock_card, diagnose_stock_mismatch
from kho_npl.filter_utils import append_filter_params, parse_int_ids
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
        or q in (r['material'].color or '').lower()
    ]


@module_perm_required(MODULE_KHO_NPL, 'view')
def overview(request):
    stats = overview_stats()
    alert_preview = stats['alert_rows'][:8]
    return render(request, 'kho_npl/overview.html', {
        **nav_context('overview', user=request.user),
        **perm_context(request.user, 'overview'),
        'stats': stats,
        'alert_preview': alert_preview,
        'alert_preview_total': len(stats['alert_rows']),
    })


def _parse_optional_date(value: str) -> date | None:
    value = (value or '').strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@module_perm_required(MODULE_KHO_NPL, 'view')
def stock_cards(request):
    search_query = get_search_query(request)
    location_ids = parse_int_ids(request, 'location')
    material_id = request.GET.get('material', '').strip()
    date_from = _parse_optional_date(request.GET.get('date_from'))
    date_to = _parse_optional_date(request.GET.get('date_to'))

    catalog_qs, _, category_ids, _ = _material_catalog_qs(request)
    stock_sum = Sum('balances__quantity')
    if location_ids:
        stock_sum = Sum('balances__quantity', filter=Q(balances__location_id__in=location_ids))
    catalog_qs = catalog_qs.annotate(stock_total=stock_sum).order_by('code')
    catalog_page, catalog_query_string = paginate_queryset(
        request, catalog_qs, per_page=20, page_param='cat_page',
    )

    selected_material = None
    card = None
    mismatch_diagnosis = None
    show_diagnosis = request.GET.get('diagnose') == '1'
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

    filter_params = []
    if date_from:
        filter_params.append(f'date_from={date_from.isoformat()}')
    if date_to:
        filter_params.append(f'date_to={date_to.isoformat()}')
    append_filter_params(filter_params, locations=location_ids, categories=category_ids)
    if search_query:
        filter_params.append(f'q={search_query}')
    catalog_filter_qs = '&'.join(filter_params)

    return render(request, 'kho_npl/stock_cards.html', {
        **nav_context('stock_cards', user=request.user),
        **perm_context(request.user, 'stock_cards'),
        'search_query': search_query,
        'locations': WarehouseLocation.objects.filter(is_active=True),
        'categories': MaterialCategory.objects.filter(is_active=True),
        'selected_locations': location_ids,
        'selected_categories': category_ids,
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
