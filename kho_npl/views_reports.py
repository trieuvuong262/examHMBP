import pandas as pd
from django.shortcuts import render
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.http import reverse
from kho_npl.reports_registry import (
    REPORT_ISSUE_DETAIL,
    REPORT_RECEIPT_DETAIL,
    REPORT_TABS,
    REPORT_XNT,
)
from kho_npl.services.excel_export import dataframe_to_xlsx_response
from kho_npl.services.issue_detail_report import (
    ISSUE_DETAIL_EXPORT_COLUMNS,
    ISSUE_DETAIL_STATUS_CHOICES,
    normalize_issue_detail_status,
    report_issue_detail,
    report_issue_detail_export_rows,
)
from kho_npl.services.receipt_detail_report import (
    RECEIPT_DETAIL_EXPORT_COLUMNS,
    RECEIPT_DETAIL_STATUS_CHOICES,
    normalize_receipt_detail_status,
    report_receipt_detail,
    report_receipt_detail_export_rows,
)
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


def _report_tabs(active: dict) -> dict:
    return {
        'report_tabs': [
            {**tab, 'url': reverse(tab['view_name']), 'active': tab['key'] == active['key']}
            for tab in REPORT_TABS
        ],
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
    export_url = reverse('kho_npl:report_export')
    if request.GET:
        export_url = f'{export_url}?{request.GET.urlencode()}'
    return render(request, 'kho_npl/report_xuat_nhap_ton.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        **_report_tabs(REPORT_XNT),
        'report': REPORT_XNT,
        'export_url': export_url,
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


def _issue_detail_filters(request):
    filters = _filter_params(request)
    filters['status'] = normalize_issue_detail_status(request.GET.get('status'))
    filters['product_code'] = (request.GET.get('product') or '').strip()
    return filters


def _issue_detail_kwargs(filters) -> dict:
    return {
        'status': filters['status'],
        'search': filters['search'],
        'product_code': filters['product_code'],
    }


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_issue_detail_view(request):
    filters = _issue_detail_filters(request)
    data = report_issue_detail(filters['date_from'], filters['date_to'], **_issue_detail_kwargs(filters))
    export_url = reverse('kho_npl:report_issue_detail_export')
    if request.GET:
        export_url = f'{export_url}?{request.GET.urlencode()}'
    return render(request, 'kho_npl/report_issue_detail.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        **_report_tabs(REPORT_ISSUE_DETAIL),
        'report': REPORT_ISSUE_DETAIL,
        'export_url': export_url,
        'filters': filters,
        'status_choices': ISSUE_DETAIL_STATUS_CHOICES,
        'printed_at': timezone.localtime(),
        'groups': data['groups'],
        'totals': data['totals'],
        'expand_all': bool(filters['search'] or filters['product_code']),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_issue_detail_export(request):
    filters = _issue_detail_filters(request)
    rows = report_issue_detail_export_rows(
        filters['date_from'], filters['date_to'], **_issue_detail_kwargs(filters),
    )
    df = pd.DataFrame(rows, columns=[label for _, label in ISSUE_DETAIL_EXPORT_COLUMNS])
    return dataframe_to_xlsx_response(df, 'Chi_tiet_xuat', 'Chi_tiet_xuat')


def _receipt_detail_filters(request):
    filters = _filter_params(request)
    filters['status'] = normalize_receipt_detail_status(request.GET.get('status'))
    filters['supplier'] = (request.GET.get('supplier') or '').strip()
    return filters


def _receipt_detail_kwargs(filters) -> dict:
    return {
        'status': filters['status'],
        'search': filters['search'],
        'supplier': filters['supplier'],
    }


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_receipt_detail_view(request):
    filters = _receipt_detail_filters(request)
    data = report_receipt_detail(filters['date_from'], filters['date_to'], **_receipt_detail_kwargs(filters))
    export_url = reverse('kho_npl:report_receipt_detail_export')
    if request.GET:
        export_url = f'{export_url}?{request.GET.urlencode()}'
    return render(request, 'kho_npl/report_receipt_detail.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        **_report_tabs(REPORT_RECEIPT_DETAIL),
        'report': REPORT_RECEIPT_DETAIL,
        'export_url': export_url,
        'filters': filters,
        'status_choices': RECEIPT_DETAIL_STATUS_CHOICES,
        'printed_at': timezone.localtime(),
        'groups': data['groups'],
        'totals': data['totals'],
        'expand_all': bool(filters['search'] or filters['supplier']),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_receipt_detail_export(request):
    filters = _receipt_detail_filters(request)
    rows = report_receipt_detail_export_rows(
        filters['date_from'], filters['date_to'], **_receipt_detail_kwargs(filters),
    )
    df = pd.DataFrame(rows, columns=[label for _, label in RECEIPT_DETAIL_EXPORT_COLUMNS])
    return dataframe_to_xlsx_response(df, 'Chi_tiet_nhap', 'Chi_tiet_nhap')
