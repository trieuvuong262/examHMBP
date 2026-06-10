from datetime import timedelta

import pandas as pd
from django.shortcuts import render
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.reports_registry import REPORT_DEFINITIONS
from kho_npl.services.excel_export import dataframe_to_xlsx_response
from kho_npl.services.reports import (
    _parse_date,
    report_alert_rows,
    report_issue_by_lsx_rows,
    report_ledger_detail_rows,
    report_movement_rows,
    report_stock_current_rows,
    report_stocktake_history_rows,
)
from kho_npl.list_columns import report_column_defs
from kho_npl.view_utils import nav_context, perm_context, report_context


def _default_date_range():
    today = timezone.localdate()
    return today - timedelta(days=30), today


def _filter_params(request):
    date_from = _parse_date(request.GET.get('date_from'))
    date_to = _parse_date(request.GET.get('date_to'))
    if not date_from and not date_to:
        date_from, date_to = _default_date_range()
    return {
        'date_from': date_from,
        'date_to': date_to,
        'material_code': (request.GET.get('material') or '').strip(),
        'lsx': (request.GET.get('lsx') or '').strip(),
    }


def _report_meta(slug: str):
    return REPORT_DEFINITIONS[slug]


def _report_table_context(rows, slug: str):
    column_labels = list(rows[0].keys()) if rows else []
    return {
        'rows': rows,
        'columns': column_labels,
        'report_column_defs': report_column_defs(column_labels),
        'table_id': f'npl-report-{slug}',
    }


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_hub(request):
    return render(request, 'kho_npl/report_hub.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        **report_context(),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_stock(request):
    rows = report_stock_current_rows()
    meta = _report_meta('ton-kho')
    return render(request, 'kho_npl/report_table.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': meta,
        'report_slug': 'ton-kho',
        'filters': {},
        **_report_table_context(rows, 'ton-kho'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_stock_export(request):
    df = pd.DataFrame(report_stock_current_rows())
    return dataframe_to_xlsx_response(df, 'Ton_kho_hien_tai', 'Ton_kho')


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_alerts(request):
    rows = report_alert_rows()
    meta = _report_meta('can-bao')
    return render(request, 'kho_npl/report_table.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': meta,
        'report_slug': 'can-bao',
        'filters': {},
        **_report_table_context(rows, 'can-bao'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_alerts_export(request):
    df = pd.DataFrame(report_alert_rows())
    return dataframe_to_xlsx_response(df, 'NPL_can_bao', 'Can_bao')


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_movement(request):
    filters = _filter_params(request)
    rows = report_movement_rows(filters['date_from'], filters['date_to'], filters['material_code'])
    meta = _report_meta('bien-dong')
    return render(request, 'kho_npl/report_table.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': meta,
        'report_slug': 'bien-dong',
        'filters': filters,
        'show_date_filter': True,
        'show_material_filter': True,
        **_report_table_context(rows, 'bien-dong'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_movement_export(request):
    filters = _filter_params(request)
    df = pd.DataFrame(report_movement_rows(
        filters['date_from'], filters['date_to'], filters['material_code'],
    ))
    return dataframe_to_xlsx_response(df, 'Bien_dong_ton', 'Bien_dong')


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_issue_lsx(request):
    filters = _filter_params(request)
    rows = report_issue_by_lsx_rows(filters['date_from'], filters['date_to'], filters['lsx'])
    meta = _report_meta('xuat-lsx')
    return render(request, 'kho_npl/report_table.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': meta,
        'report_slug': 'xuat-lsx',
        'filters': filters,
        'show_date_filter': True,
        'show_lsx_filter': True,
        **_report_table_context(rows, 'xuat-lsx'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_issue_lsx_export(request):
    filters = _filter_params(request)
    df = pd.DataFrame(report_issue_by_lsx_rows(
        filters['date_from'], filters['date_to'], filters['lsx'],
    ))
    return dataframe_to_xlsx_response(df, 'Xuat_theo_LSX', 'Xuat_LSX')


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_stocktake_history(request):
    rows = report_stocktake_history_rows()
    meta = _report_meta('kiem-ke')
    return render(request, 'kho_npl/report_table.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': meta,
        'report_slug': 'kiem-ke',
        'filters': {},
        **_report_table_context(rows, 'kiem-ke'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_stocktake_history_export(request):
    df = pd.DataFrame(report_stocktake_history_rows())
    return dataframe_to_xlsx_response(df, 'Lich_su_kiem_ke', 'Kiem_ke')


@module_perm_required(MODULE_KHO_NPL, 'view')
def report_ledger(request):
    filters = _filter_params(request)
    rows = report_ledger_detail_rows(filters['date_from'], filters['date_to'], filters['material_code'])
    meta = _report_meta('so-kho')
    return render(request, 'kho_npl/report_table.html', {
        **nav_context('reports', user=request.user),
        **perm_context(request.user, 'reports'),
        'report': meta,
        'report_slug': 'so-kho',
        'filters': filters,
        'show_date_filter': True,
        'show_material_filter': True,
        **_report_table_context(rows, 'so-kho'),
    })


@module_perm_required(MODULE_KHO_NPL, 'export')
def report_ledger_export(request):
    filters = _filter_params(request)
    df = pd.DataFrame(report_ledger_detail_rows(
        filters['date_from'], filters['date_to'], filters['material_code'],
    ))
    return dataframe_to_xlsx_response(df, 'So_kho_chi_tiet', 'So_kho')
