import pandas as pd
from django.shortcuts import render
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.reports_registry import REPORT_XNT
from kho_npl.services.excel_export import dataframe_to_xlsx_response
from kho_npl.services.reports import (
    DISPLAY_LIMIT,
    _parse_date,
    location_scope_label,
    report_xuat_nhap_ton,
    report_xuat_nhap_ton_export_rows,
)
from kho_npl.services.scrap_warehouse import source_locations_qs
from kho_npl.view_utils import nav_context, perm_context
from utilities.date_range_filter import (
    date_range_from_span,
    date_range_span_context,
    parse_date_range_span_from_request,
)


def _parse_location_id(raw) -> int | None:
    value = (raw or '').strip()
    if value.isdigit():
        loc_id = int(value)
        if source_locations_qs().filter(pk=loc_id).exists():
            return loc_id
    return None


def _filter_params(request):
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    span = parse_date_range_span_from_request(request, default=30)
    if not date_to:
        date_to = timezone.localdate()
    if not date_from:
        date_from = date_range_from_span(date_to, span)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    location_id = _parse_location_id(request.GET.get('location'))
    return {
        'date_from': date_from,
        'date_to': date_to,
        'location_id': location_id,
        'search': (request.GET.get('q') or '').strip(),
        **date_range_span_context(date_from, date_to),
    }


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_hub(request):
    filters = _filter_params(request)
    data = report_xuat_nhap_ton(
        filters['date_from'],
        filters['date_to'],
        location_id=filters['location_id'],
        search=filters['search'],
        limit=DISPLAY_LIMIT,
    )
    return render(request, 'kho_npl/report_xuat_nhap_ton.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': REPORT_XNT,
        'filters': filters,
        'locations': source_locations_qs().order_by('name', 'code'),
        'scope_label': location_scope_label(filters['location_id']),
        'printed_at': timezone.localtime(),
        'groups': data['groups'],
        'totals': data['totals'],
        'total_count': data['total_count'],
        'sku_count': data['sku_count'],
        'displayed_count': data['displayed_count'],
        'truncated': data['truncated'],
        'display_limit': data['display_limit'],
        'expand_search_hits': bool(filters['search']),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_export(request):
    filters = _filter_params(request)
    rows = report_xuat_nhap_ton_export_rows(
        filters['date_from'],
        filters['date_to'],
        location_id=filters['location_id'],
        search=filters['search'],
    )
    df = pd.DataFrame(rows)
    return dataframe_to_xlsx_response(df, 'Xuat_nhap_ton', 'Xuat_nhap_ton')
