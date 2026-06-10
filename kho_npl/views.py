from django.shortcuts import redirect, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.services.stock import overview_stats
from kho_npl.view_utils import nav_context, perm_context
from kho_npl.views_settings import settings_hub_items


@module_perm_required(MODULE_KHO_NPL, 'view')
def overview(request):
    stats = overview_stats()
    search_query = get_search_query(request)
    rows = stats['alert_rows']
    if search_query:
        q = search_query.lower()
        rows = [
            r for r in rows
            if q in r['material'].code.lower()
            or q in r['material'].name.lower()
            or q in (r['material'].color or '').lower()
        ]
    page_obj, query_string = paginate_queryset(request, rows, per_page=20)
    return render(request, 'kho_npl/overview.html', {
        **nav_context('overview'),
        **perm_context(request.user),
        'stats': stats,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
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
