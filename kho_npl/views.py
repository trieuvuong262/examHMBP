from django.shortcuts import redirect, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.choices import STOCK_STATUS_LOW, STOCK_STATUS_OK, STOCK_STATUS_OUT
from kho_npl.models import MaterialCategory, WarehouseLocation
from kho_npl.services.stock import (
    balance_stock_rows,
    material_stock_rows,
    overview_stats,
    stock_rows_for_status,
)
from kho_npl.view_utils import nav_context, perm_context
from kho_npl.views_settings import settings_hub_items

STOCK_ALERT_STATUS_CHOICES = {
    STOCK_STATUS_LOW: {
        'title': 'NPL sắp thiếu',
        'subtitle': 'Tồn còn nhưng đã xuống dưới hoặc bằng mức tối thiểu.',
        'icon': 'bi-exclamation-triangle',
        'badge': 'warning',
    },
    STOCK_STATUS_OUT: {
        'title': 'NPL hết hàng',
        'subtitle': 'Tồn bằng 0 — cần nhập hoặc điều chỉnh kịp thời.',
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
        **nav_context('overview'),
        **perm_context(request.user),
        'stats': stats,
        'alert_preview': alert_preview,
        'alert_preview_total': len(stats['alert_rows']),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def stock_cards(request):
    search_query = get_search_query(request)
    location_id = request.GET.get('location', '').strip()
    category_id = request.GET.get('category', '').strip()
    status = (request.GET.get('status') or '').strip().lower()
    if status not in (STOCK_STATUS_OK, STOCK_STATUS_LOW, STOCK_STATUS_OUT):
        status = ''

    rows = balance_stock_rows(
        location_id=int(location_id) if location_id.isdigit() else None,
        category_id=int(category_id) if category_id.isdigit() else None,
        status_filter=status or None,
        search_query=search_query,
    )
    page_obj, query_string = paginate_queryset(request, rows, per_page=30)
    return render(request, 'kho_npl/stock_cards.html', {
        **nav_context('stock_cards'),
        **perm_context(request.user),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'locations': WarehouseLocation.objects.filter(is_active=True),
        'categories': MaterialCategory.objects.filter(is_active=True),
        'selected_location': location_id,
        'selected_category': category_id,
        'selected_status': status,
        'total_rows': len(rows),
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
        page_subtitle = meta['subtitle']
        page_icon = meta['icon']
    else:
        page_title = 'Cảnh báo tồn kho'
        page_subtitle = 'NPL sắp thiếu và hết hàng.'
        page_icon = 'bi-exclamation-triangle'

    return render(request, 'kho_npl/stock_alerts.html', {
        **nav_context('overview'),
        **perm_context(request.user),
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_status': status,
        'status_choices': STOCK_ALERT_STATUS_CHOICES,
        'page_title': page_title,
        'page_subtitle': page_subtitle,
        'page_icon': page_icon,
        'total_count': len(rows),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def settings_hub(request):
    return render(request, 'kho_npl/settings_hub.html', {
        **nav_context('settings'),
        **perm_context(request.user),
        'settings_items': settings_hub_items(),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def hub_redirect(request):
    return redirect('kho_npl:overview')
