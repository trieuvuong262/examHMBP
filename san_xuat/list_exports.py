"""Registry xuất Excel danh sách Sản xuất — key → builder rows / sheets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
from django.http import HttpRequest, HttpResponse

from san_xuat.list_filters import (
    SX_FILTER_ACTUAL_COST,
    SX_FILTER_BOM,
    SX_FILTER_COST_ORDER,
    SX_FILTER_COST_SHEET,
    SX_FILTER_COST_TYPE,
    SX_FILTER_DISASSEMBLY,
    SX_FILTER_DOWNTIME,
    SX_FILTER_FG_RECEIPT,
    SX_FILTER_MATERIAL_ISSUE,
    SX_FILTER_MO,
    SX_FILTER_NCR,
    SX_FILTER_NPL_PR,
    SX_FILTER_NPL_SURPLUS,
    SX_FILTER_PACKING,
    SX_FILTER_PLAN_NPL,
    SX_FILTER_PLAN_PERIOD,
    SX_FILTER_PROD_STAT,
    SX_FILTER_PURCHASE_ORDER,
    SX_FILTER_QC_ALERT,
    SX_FILTER_QC_REQUEST,
    SX_FILTER_QC_SHEET,
    SX_FILTER_SUBCONTRACT,
    SX_FILTER_WIP_HANDOVER,
    SX_FILTER_WIP_RETURN,
    SX_FILTER_WORK_ASSIGN,
    SX_FILTER_WORK_CENTER,
    apply_sx_list_filters,
    filter_tuple_rows,
    parse_sx_list_filters,
    SxFilterSpec,
    SxListFilters,
)
from san_xuat.services.excel_export import (
    dataframe_to_xlsx_response,
    dataframes_to_xlsx_response,
)

EXPORT_ROW_LIMIT = 5000


def _status(obj) -> str:
    fn = getattr(obj, 'get_status_display', None)
    if callable(fn):
        return str(fn())
    return str(getattr(obj, 'status', '') or '')


def _d(val) -> str:
    if val is None:
        return ''
    if hasattr(val, 'strftime'):
        try:
            return val.strftime('%d/%m/%Y')
        except Exception:
            return str(val)
    return str(val)


def _filtered(request: HttpRequest, qs, spec: SxFilterSpec):
    filters = parse_sx_list_filters(request)
    if hasattr(qs.model, 'created_by_id'):
        qs = qs.select_related('created_by')
    return apply_sx_list_filters(qs, filters, spec)[:EXPORT_ROW_LIMIT]


def _rows_to_response(rows: list[dict], filename: str, sheet: str = 'Danh_sach') -> HttpResponse:
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return dataframe_to_xlsx_response(df, filename, sheet_name=sheet)


# --- Builders ---


def _export_doc_list(request: HttpRequest) -> HttpResponse:
    from PortalJustPlay.list_search import apply_term_search, get_search_query
    from san_xuat.models import ProductTechDoc

    qs = ProductTechDoc.objects.all().order_by('-updated_at', '-pk')
    qs = apply_term_search(
        qs,
        get_search_query(request),
        'product_code__icontains',
        'product_name__icontains',
        'notes__icontains',
    )[:EXPORT_ROW_LIMIT]
    rows = [
        {
            'Mã SP': d.product_code,
            'Tên SP': d.product_name,
            'Trạng thái': _status(d) if hasattr(d, 'status') else '',
            'Cập nhật': _d(getattr(d, 'updated_at', None)),
        }
        for d in qs
    ]
    return _rows_to_response(rows, 'Ho_so_SX', 'Ho_so')


def _export_bom_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Count

    from san_xuat.models import BomVersion

    qs = (
        BomVersion.objects.select_related('tech_doc')
        .annotate(line_count=Count('lines'), step_count=Count('process_steps'))
        .order_by('-updated_at', '-pk')
    )
    status = (request.GET.get('status') or '').strip()
    if status:
        qs = qs.filter(status=status)
    qs = _filtered(request, qs, SX_FILTER_BOM)
    rows = []
    for b in qs:
        doc = b.tech_doc
        rows.append({
            'Mã SP': getattr(doc, 'product_code', '') if doc else '',
            'Tên SP': getattr(doc, 'product_name', '') if doc else '',
            'Phiên bản': b.version_label or b.version or '',
            'Trạng thái': _status(b),
            'Số NVL': getattr(b, 'line_count', 0),
            'Số công đoạn': getattr(b, 'step_count', 0),
            'Cập nhật': _d(b.updated_at),
        })
    return _rows_to_response(rows, 'BOM_dinh_muc', 'BOM')


def _export_capacity(request: HttpRequest) -> HttpResponse:
    from san_xuat.hub_models import SxWorkCenter
    from san_xuat.list_filters import resolve_sx_period
    from san_xuat.services.phase3 import build_capacity_load

    month = (request.GET.get('month') or '').strip()
    date_from, date_to, filters = resolve_sx_period(request)

    base = SxWorkCenter.objects.filter(is_demo=False).order_by('code')
    centers = apply_sx_list_filters(base, filters, SX_FILTER_WORK_CENTER)[:EXPORT_ROW_LIMIT]
    load_rows = build_capacity_load(date_from=date_from, date_to=date_to)

    center_rows = [
        {
            'Mã': c.code,
            'Tên': c.name,
            'Nhãn tổ': c.team_label or '',
            'NL/ngày': float(c.capacity_per_day or 0),
            'ĐVT': c.uom_label or '',
            'Trạng thái': 'Đang dùng' if c.is_active else 'Tắt',
        }
        for c in centers
    ]
    load_sheet = []
    for row in load_rows:
        center = row.center
        load_sheet.append({
            'Tổ/chuyền': f'{getattr(center, "code", "")} — {getattr(center, "name", "")}',
            'NL kỳ': float(row.capacity_period or 0),
            'Còn lại': float(row.assigned_open or 0),
            'Tải %': row.load_pct or 0,
            'SX đạt kỳ': float(row.output_period or 0),
            'Tận dụng %': row.utilization_pct or 0,
        })
    return dataframes_to_xlsx_response(
        {
            'Tai_ky': pd.DataFrame(load_sheet),
            'Danh_muc': pd.DataFrame(center_rows),
        },
        'Nang_luc_SX',
    )


def _hub_model_export(
    request: HttpRequest,
    *,
    model,
    spec: SxFilterSpec,
    filename: str,
    row_fn: Callable[[Any], dict],
    base_qs=None,
    order_by=('-pk',),
    select_related=(),
):
    qs = base_qs if base_qs is not None else model.objects.filter(is_demo=False)
    if select_related:
        qs = qs.select_related(*select_related)
    if order_by:
        qs = qs.order_by(*order_by)
    qs = _filtered(request, qs, spec)
    return _rows_to_response([row_fn(obj) for obj in qs], filename)


def _export_plan_overall(request):
    from san_xuat.hub_models import SxOverallPlan

    return _hub_model_export(
        request,
        model=SxOverallPlan,
        spec=SX_FILTER_PLAN_PERIOD,
        filename='Ke_hoach_tong_the',
        order_by=('-date_from', '-pk'),
        row_fn=lambda p: {
            'Mã': p.code,
            'Tên': p.name,
            'Từ ngày': _d(p.date_from),
            'Đến ngày': _d(p.date_to),
            'Nguồn': getattr(p, 'source', '') or '',
            'Trạng thái': _status(p),
        },
    )


def _export_plan_detail(request):
    from san_xuat.hub_models import SxDetailPlan

    return _hub_model_export(
        request,
        model=SxDetailPlan,
        spec=SX_FILTER_PLAN_PERIOD,
        filename='Ke_hoach_chi_tiet',
        order_by=('-date_from', '-pk'),
        select_related=('overall_plan',),
        row_fn=lambda p: {
            'Mã': p.code,
            'Tên': p.name,
            'KH tổng thể': getattr(p.overall_plan, 'code', '') if p.overall_plan_id else '',
            'Từ ngày': _d(p.date_from),
            'Đến ngày': _d(p.date_to),
            'Trạng thái': _status(p),
        },
    )


def _export_plan_npl(request):
    from san_xuat.hub_models import SxMaterialPlan

    return _hub_model_export(
        request,
        model=SxMaterialPlan,
        spec=SX_FILTER_PLAN_NPL,
        filename='Ke_hoach_NPL',
        order_by=('-created_at', '-pk'),
        select_related=('overall_plan',),
        row_fn=lambda p: {
            'Mã': p.code,
            'Tên': p.name,
            'KH tổng thể': getattr(p.overall_plan, 'code', '') if p.overall_plan_id else '',
            'Trạng thái': _status(p),
        },
    )


def _export_npl_pr(request):
    from san_xuat.hub_models import SxNplPurchaseRequest

    return _hub_model_export(
        request,
        model=SxNplPurchaseRequest,
        spec=SX_FILTER_NPL_PR,
        filename='Yeu_cau_mua_NPL',
        order_by=('-request_date', '-pk'),
        select_related=('material_plan',),
        row_fn=lambda r: {
            'Mã': r.code,
            'KH NPL': getattr(r.material_plan, 'code', '') if r.material_plan_id else '',
            'Ngày YC': _d(r.request_date),
            'Hạn': _d(getattr(r, 'due_date', None)),
            'Ghi chú': getattr(r, 'notes', '') or '',
            'Trạng thái': _status(r),
        },
    )


def _export_purchase_order(request):
    from san_xuat.hub_models import SxPurchaseOrder

    return _hub_model_export(
        request,
        model=SxPurchaseOrder,
        spec=SX_FILTER_PURCHASE_ORDER,
        filename='Don_mua_hang',
        order_by=('-created_at', '-pk'),
        select_related=('purchase_request',),
        row_fn=lambda o: {
            'Mã': o.code,
            'NCC': o.supplier_name or '',
            'YCM': getattr(o.purchase_request, 'code', '') if o.purchase_request_id else '',
            'Trạng thái': _status(o),
        },
    )


def _export_dispatch_mo(request):
    from san_xuat.hub_models import SxProductionOrder

    return _hub_model_export(
        request,
        model=SxProductionOrder,
        spec=SX_FILTER_MO,
        filename='Lenh_san_xuat',
        order_by=('-order_date', '-pk'),
        row_fn=lambda o: {
            'Mã': o.code,
            'Sản phẩm': f'{o.product_code} — {o.product_name}'.strip(' —'),
            'Số lượng': float(o.qty or 0),
            'Ngày': _d(o.order_date),
            'Hạn': _d(o.due_date),
            'Trạng thái': _status(o),
        },
    )


def _export_disassembly(request):
    from san_xuat.hub_models import SxDisassemblyOrder

    return _hub_model_export(
        request,
        model=SxDisassemblyOrder,
        spec=SX_FILTER_DISASSEMBLY,
        filename='Lenh_thao_do',
        order_by=('-order_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda o: {
            'Mã': o.code,
            'Sản phẩm': f'{getattr(o, "product_code", "")} — {getattr(o, "product_name", "")}'.strip(' —'),
            'Số lượng': float(getattr(o, 'qty', 0) or 0),
            'LSX': getattr(o.production_order, 'code', '') if getattr(o, 'production_order_id', None) else '',
            'Ngày': _d(getattr(o, 'order_date', None)),
            'Trạng thái': _status(o),
        },
    )


def _export_material_issue(request):
    from san_xuat.hub_models import SxMaterialIssueRequest
    from san_xuat.services.mo_progress import pending_material_issue_qs

    queue = (request.GET.get('queue') or '').strip().lower()
    if queue in ('pending', 'cho-duyet', '1'):
        base = pending_material_issue_qs()
    else:
        base = SxMaterialIssueRequest.objects.filter(is_demo=False)
    base = base.select_related('production_order', 'stock_issue').order_by('-request_date', '-pk')
    qs = _filtered(request, base, SX_FILTER_MATERIAL_ISSUE)
    rows = [
        {
            'Mã': r.code,
            'LSX': getattr(r.production_order, 'code', '') if r.production_order_id else '',
            'Ngày YC': _d(r.request_date),
            'Trạng thái': _status(r),
            'Phiếu kho': getattr(r.stock_issue, 'code', '') if r.stock_issue_id else '',
        }
        for r in qs
    ]
    return _rows_to_response(rows, 'Yeu_cau_xuat_VT', 'YCX')


def _export_prod_stats(request):
    from san_xuat.hub_models import SxProductionStat

    return _hub_model_export(
        request,
        model=SxProductionStat,
        spec=SX_FILTER_PROD_STAT,
        filename='Thong_ke_SX',
        order_by=('-stat_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda s: {
            'Mã': s.code,
            'LSX': getattr(s.production_order, 'code', '') if s.production_order_id else '',
            'Ngày': _d(s.stat_date),
            'Công đoạn': s.process_name or '',
            'Đạt': float(s.qty_good or 0),
            'Lỗi': float(s.qty_defect or 0),
            'Trạng thái': _status(s),
        },
    )


def _export_fg_receipt(request):
    from san_xuat.hub_models import SxFgReceiptRequest

    return _hub_model_export(
        request,
        model=SxFgReceiptRequest,
        spec=SX_FILTER_FG_RECEIPT,
        filename='Yeu_cau_nhap_TP',
        order_by=('-request_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda r: {
            'Mã': r.code,
            'LSX': getattr(r.production_order, 'code', '') if r.production_order_id else '',
            'Ngày YC': _d(r.request_date),
            'Số lượng': float(getattr(r, 'qty', 0) or 0),
            'Trạng thái': _status(r),
        },
    )


def _export_npl_surplus(request):
    from san_xuat.hub_models import SxNplSurplus

    return _hub_model_export(
        request,
        model=SxNplSurplus,
        spec=SX_FILTER_NPL_SURPLUS,
        filename='NPL_thua',
        order_by=('-recorded_at', '-pk'),
        select_related=('production_order',),
        row_fn=lambda x: {
            'Mã': x.code,
            'NVL': getattr(x, 'material_code', '') or getattr(x, 'material_name', '') or '',
            'SL': float(getattr(x, 'qty', 0) or 0),
            'LSX': getattr(x.production_order, 'code', '') if getattr(x, 'production_order_id', None) else '',
            'Ngày': _d(getattr(x, 'recorded_at', None)),
            'Trạng thái': _status(x),
        },
    )


def _export_wip_handover(request):
    from san_xuat.hub_models import SxWipHandover

    return _hub_model_export(
        request,
        model=SxWipHandover,
        spec=SX_FILTER_WIP_HANDOVER,
        filename='Ban_giao_BTP',
        order_by=('-handover_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda h: {
            'Mã': h.code,
            'LSX': getattr(h.production_order, 'code', '') if h.production_order_id else '',
            'Từ CĐ': getattr(h, 'from_process', '') or '',
            'Đến CĐ': getattr(h, 'to_process', '') or '',
            'SL': float(getattr(h, 'qty', 0) or 0),
            'Ngày': _d(h.handover_date),
            'Trạng thái': _status(h),
        },
    )


def _export_wip_return(request):
    from san_xuat.hub_models import SxWipReturn

    return _hub_model_export(
        request,
        model=SxWipReturn,
        spec=SX_FILTER_WIP_RETURN,
        filename='Tra_lai_BTP',
        order_by=('-return_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda r: {
            'Mã': r.code,
            'LSX': getattr(r.production_order, 'code', '') if r.production_order_id else '',
            'Từ CĐ': getattr(r, 'from_process', '') or '',
            'Đến CĐ': getattr(r, 'to_process', '') or '',
            'SL': float(getattr(r, 'qty', 0) or 0),
            'Ngày': _d(r.return_date),
            'Trạng thái': _status(r),
        },
    )


def _export_qc_request(request):
    from san_xuat.hub_models import SxQcRequest

    return _hub_model_export(
        request,
        model=SxQcRequest,
        spec=SX_FILTER_QC_REQUEST,
        filename='Yeu_cau_QC',
        order_by=('-created_at', '-pk'),
        select_related=('production_order',),
        row_fn=lambda r: {
            'Mã': r.code,
            'LSX': getattr(r.production_order, 'code', '') if r.production_order_id else '',
            'Mã SP': getattr(r, 'product_code', '') or '',
            'Công đoạn': getattr(r, 'stage_name', '') or '',
            'SL': float(getattr(r, 'qty', 0) or 0),
            'Trạng thái': _status(r),
        },
    )


def _export_qc_sheet(request):
    from san_xuat.hub_models import SxQcInspection

    return _hub_model_export(
        request,
        model=SxQcInspection,
        spec=SX_FILTER_QC_SHEET,
        filename='Phieu_QC',
        order_by=('-inspected_at', '-pk'),
        select_related=('qc_request', 'standard_set'),
        row_fn=lambda i: {
            'Mã': i.code,
            'YC QC': getattr(i.qc_request, 'code', '') if i.qc_request_id else '',
            'Ngày KT': _d(i.inspected_at),
            'Bộ TC': getattr(i.standard_set, 'code', '') if getattr(i, 'standard_set_id', None) else '',
            'Mẫu': getattr(i, 'qty_sample', '') or '',
            'Đạt': getattr(i, 'qty_pass', '') or '',
            'Lỗi': getattr(i, 'qty_fail', '') or '',
            'Kết luận': getattr(i, 'result', '') or '',
            'Trạng thái': _status(i),
        },
    )


def _export_qc_alerts(request):
    from san_xuat.hub_models import SxQcAlert

    base = (
        SxQcAlert.objects.filter(is_demo=False)
        .select_related('production_order')
        .order_by('-created_at', '-pk')
    )
    status = (request.GET.get('status') or '').strip()
    if status:
        base = base.filter(status=status)
    qs = _filtered(request, base, SX_FILTER_QC_ALERT)
    rows = [
        {
            'Mã': a.code,
            'Loại': getattr(a, 'alert_type', '') or '',
            'LSX': getattr(a.production_order, 'code', '') if a.production_order_id else '',
            'Công đoạn': a.process_name or '',
            'Tỷ lệ lỗi': float(a.defect_rate or 0),
            'Ngưỡng': float(a.tolerance_limit or 0),
            'Trạng thái': _status(a),
        }
        for a in qs
    ]
    return _rows_to_response(rows, 'Canh_bao_QC', 'Canh_bao')


def _qc_catalog_export(model, filename: str, columns: list[tuple[str, str]]):
    def _builder(request: HttpRequest) -> HttpResponse:
        qs = model.objects.filter(is_demo=False).order_by('code')[:EXPORT_ROW_LIMIT]
        rows = []
        for obj in qs:
            row = {}
            for label, attr in columns:
                val = getattr(obj, attr, '')
                if attr == 'is_active':
                    val = 'Có' if val else 'Không'
                elif callable(getattr(obj, f'get_{attr}_display', None)):
                    val = getattr(obj, f'get_{attr}_display')()
                elif hasattr(val, 'code'):
                    val = val.code
                row[label] = val if val is not None else ''
            rows.append(row)
        return _rows_to_response(rows, filename)

    return _builder


def _export_costing_sheet(request):
    from san_xuat.hub_models import SxStandardCostSheet

    return _hub_model_export(
        request,
        model=SxStandardCostSheet,
        spec=SX_FILTER_COST_SHEET,
        filename='Bang_gia_thanh_DM',
        order_by=('-date_from', '-pk'),
        row_fn=lambda s: {
            'Mã': s.code,
            'Tên': s.name,
            'Từ ngày': _d(s.date_from),
            'Đến ngày': _d(s.date_to),
            'Trạng thái': _status(s),
        },
    )


def _export_costing_order(request):
    from san_xuat.hub_models import SxOrderPlanCost

    return _hub_model_export(
        request,
        model=SxOrderPlanCost,
        spec=SX_FILTER_COST_ORDER,
        filename='Gia_thanh_theo_don',
        order_by=('-date_from', '-pk'),
        row_fn=lambda s: {
            'Mã': s.code,
            'Tên': s.name,
            'Mã đơn KV': getattr(s, 'kv_order_code', '') or '',
            'Từ ngày': _d(s.date_from),
            'Đến ngày': _d(s.date_to),
            'Tổng GTKH': float(getattr(s, 'total_cost', 0) or 0),
            'Trạng thái': _status(s),
        },
    )


def _export_cost_types(request):
    from san_xuat.hub_models import SxCostType

    return _hub_model_export(
        request,
        model=SxCostType,
        spec=SX_FILTER_COST_TYPE,
        filename='Loai_chi_phi',
        order_by=('sort_order', 'code'),
        row_fn=lambda t: {
            'Mã': t.code,
            'Tên': t.name,
            'Thứ tự': getattr(t, 'sort_order', 0) or 0,
            'Trạng thái': 'Đang dùng' if getattr(t, 'is_active', True) else 'Tắt',
        },
    )


def _export_costing_norm(request):
    from san_xuat.services.costing import list_costing_from_active_boms

    filters = parse_sx_list_filters(request)
    tuples = filter_tuple_rows(
        list_costing_from_active_boms(),
        filters,
        date_index=1,
        date_attr='updated_at',
    )[:EXPORT_ROW_LIMIT]
    rows = []
    for item in tuples:
        doc = item[0]
        result = item[2] if len(item) > 2 else None
        rows.append({
            'Mã SP': getattr(doc, 'product_code', ''),
            'Tên SP': getattr(doc, 'product_name', ''),
            'NVL': float(getattr(result, 'material_cost', 0) or 0) if result else 0,
            'Nhân công': float(getattr(result, 'labor_cost', 0) or 0) if result else 0,
            'Chi phí chung': float(getattr(result, 'overhead_cost', 0) or 0) if result else 0,
            'Tổng': float(getattr(result, 'total_cost', 0) or 0) if result else 0,
            'Giá bán': float(getattr(result, 'sell_price', 0) or 0) if result else 0,
            'Biên LN': float(getattr(result, 'margin_pct', 0) or 0) if result else 0,
        })
    return _rows_to_response(rows, 'Gia_thanh_dinh_muc', 'Dinh_muc')


def _export_actual_cost(request):
    from san_xuat.hub_models import SxActualCostSheet

    return _hub_model_export(
        request,
        model=SxActualCostSheet,
        spec=SX_FILTER_ACTUAL_COST,
        filename='Gia_thanh_thuc_te',
        order_by=('-created_at', '-pk'),
        select_related=('production_order',),
        row_fn=lambda s: {
            'Mã': s.code,
            'LSX': getattr(s.production_order, 'code', '') if getattr(s, 'production_order_id', None) else '',
            'NVL': float(getattr(s, 'material_cost', 0) or 0),
            'Nhân công': float(getattr(s, 'labor_cost', 0) or 0),
            'Gia công': float(getattr(s, 'subcontract_cost', 0) or 0),
            'Tổng': float(getattr(s, 'total_cost', 0) or 0),
            'Trạng thái': _status(s),
        },
    )


def _export_work_assign(request):
    from san_xuat.hub_models import SxWorkAssignment

    qs = (
        SxWorkAssignment.objects.filter(is_demo=False)
        .select_related('production_order', 'work_center', 'work_task', 'assignee')
        .order_by('-created_at', '-pk')
    )
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)
    qs = _filtered(request, qs, SX_FILTER_WORK_ASSIGN)
    rows = [
        {
            'Mã': a.code,
            'LSX': getattr(a.production_order, 'code', '') if a.production_order_id else '',
            'Tiêu đề': a.title or '',
            'Tổ': getattr(a.work_center, 'code', '') if a.work_center_id else (a.assignee_label or ''),
            'Công đoạn': a.process_name or '',
            'Người nhận': (
                getattr(a.assignee, 'get_full_name', lambda: '')()
                or getattr(a.assignee, 'username', '')
                if a.assignee_id else (a.assignee_label or '')
            ),
            'Hạn': _d(a.due_date),
            'Trạng thái': _status(a),
        }
        for a in qs
    ]
    return _rows_to_response(rows, 'Giao_viec_SX', 'Giao_viec')


def _export_packing(request):
    from san_xuat.hub_models import SxPackingRecord

    return _hub_model_export(
        request,
        model=SxPackingRecord,
        spec=SX_FILTER_PACKING,
        filename='Dong_goi',
        order_by=('-pack_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda p: {
            'Mã': p.code,
            'LSX': getattr(p.production_order, 'code', '') if p.production_order_id else '',
            'SL': float(p.qty or 0),
            'Lô': p.lot_code or '',
            'Ngày đóng': _d(p.pack_date),
            'Trạng thái': _status(p),
        },
    )


def _export_subcontract(request):
    from san_xuat.hub_models import SxSubcontractOrder

    return _hub_model_export(
        request,
        model=SxSubcontractOrder,
        spec=SX_FILTER_SUBCONTRACT,
        filename='Thue_gia_cong',
        order_by=('-order_date', '-pk'),
        row_fn=lambda o: {
            'Mã': o.code,
            'NCC': o.vendor_name or '',
            'Sản phẩm': f'{getattr(o, "product_code", "")} — {getattr(o, "product_name", "")}'.strip(' —'),
            'SL': float(getattr(o, 'qty', 0) or 0),
            'Ngày': _d(o.order_date),
            'Trạng thái': _status(o),
        },
    )


def _export_ncr(request):
    from san_xuat.hub_models import SxNcrCase

    return _hub_model_export(
        request,
        model=SxNcrCase,
        spec=SX_FILTER_NCR,
        filename='NCR',
        order_by=('-created_at', '-pk'),
        select_related=('production_order',),
        row_fn=lambda c: {
            'Mã': c.code,
            'LSX': getattr(c.production_order, 'code', '') if c.production_order_id else '',
            'Xử lý': getattr(c, 'disposition', '') or '',
            'SL': float(c.qty or 0),
            'Trạng thái': _status(c),
        },
    )


def _export_downtime(request):
    from san_xuat.hub_models import SxDowntimeEvent

    return _hub_model_export(
        request,
        model=SxDowntimeEvent,
        spec=SX_FILTER_DOWNTIME,
        filename='Dung_chuyen',
        order_by=('-event_date', '-pk'),
        select_related=('production_order',),
        row_fn=lambda e: {
            'Mã': e.code,
            'Ngày': _d(e.event_date),
            'Lý do': getattr(e, 'reason', '') or '',
            'Phút': getattr(e, 'minutes', 0) or 0,
            'Tổ': getattr(e, 'team_label', '') or '',
            'LSX': getattr(e.production_order, 'code', '') if getattr(e, 'production_order_id', None) else '',
        },
    )


@dataclass(frozen=True)
class ListExportSpec:
    key: str
    builder: Callable[[HttpRequest], HttpResponse]


def _build_registry() -> dict[str, ListExportSpec]:
    from san_xuat.hub_models import (
        SxQcCriteria,
        SxQcCriteriaGroup,
        SxQcDefect,
        SxQcDefectGroup,
        SxQcSamplingMethod,
        SxQcStandardSet,
    )

    specs = [
        ListExportSpec('doc_list', _export_doc_list),
        ListExportSpec('bom_list', _export_bom_list),
        ListExportSpec('capacity_list', _export_capacity),
        ListExportSpec('plan_overall', _export_plan_overall),
        ListExportSpec('plan_detail', _export_plan_detail),
        ListExportSpec('plan_npl', _export_plan_npl),
        ListExportSpec('npl_purchase_request', _export_npl_pr),
        ListExportSpec('purchase_order', _export_purchase_order),
        ListExportSpec('dispatch_mo', _export_dispatch_mo),
        ListExportSpec('dispatch_disassembly', _export_disassembly),
        ListExportSpec('dispatch_material_issue_req', _export_material_issue),
        ListExportSpec('dispatch_prod_stats', _export_prod_stats),
        ListExportSpec('dispatch_fg_receipt_req', _export_fg_receipt),
        ListExportSpec('dispatch_npl_surplus', _export_npl_surplus),
        ListExportSpec('dispatch_wip_handover', _export_wip_handover),
        ListExportSpec('dispatch_wip_return', _export_wip_return),
        ListExportSpec('qc_request', _export_qc_request),
        ListExportSpec('qc_sheet', _export_qc_sheet),
        ListExportSpec('qc_alerts', _export_qc_alerts),
        ListExportSpec(
            'qc_criteria',
            _qc_catalog_export(
                SxQcCriteria, 'Tieu_chi_QC',
                [('Mã', 'code'), ('Tên', 'name'), ('Nhóm', 'group'), ('Loại', 'kind')],
            ),
        ),
        ListExportSpec(
            'qc_criteria_group',
            _qc_catalog_export(
                SxQcCriteriaGroup, 'Nhom_tieu_chi_QC',
                [('Mã', 'code'), ('Tên', 'name'), ('Active', 'is_active')],
            ),
        ),
        ListExportSpec(
            'qc_sampling',
            _qc_catalog_export(
                SxQcSamplingMethod, 'Chon_mau_QC',
                [('Mã', 'code'), ('Tên', 'name'), ('Kiểu', 'method_type'), ('Giá trị', 'sample_value')],
            ),
        ),
        ListExportSpec(
            'qc_standard_set',
            _qc_catalog_export(
                SxQcStandardSet, 'Bo_tieu_chuan_QC',
                [
                    ('Mã', 'code'), ('Tên', 'name'), ('Mã SP', 'product_code'),
                    ('Công đoạn', 'stage_name'), ('Ngưỡng lỗi %', 'defect_tolerance_pct'),
                    ('Chọn mẫu', 'sampling_method'),
                ],
            ),
        ),
        ListExportSpec(
            'qc_defect',
            _qc_catalog_export(
                SxQcDefect, 'Loi_QC',
                [('Mã', 'code'), ('Tên', 'name'), ('Nhóm', 'group'), ('Mức', 'severity')],
            ),
        ),
        ListExportSpec(
            'qc_defect_group',
            _qc_catalog_export(
                SxQcDefectGroup, 'Nhom_loi_QC',
                [('Mã', 'code'), ('Tên', 'name'), ('Active', 'is_active')],
            ),
        ),
        ListExportSpec('costing_sheet_list', _export_costing_sheet),
        ListExportSpec('costing_order_list', _export_costing_order),
        ListExportSpec('costing_cost_types', _export_cost_types),
        ListExportSpec('costing_norm', _export_costing_norm),
        ListExportSpec('actual_cost_list', _export_actual_cost),
        ListExportSpec('work_assignment_list', _export_work_assign),
        ListExportSpec('packing_list', _export_packing),
        ListExportSpec('subcontract_list', _export_subcontract),
        ListExportSpec('ncr_list', _export_ncr),
        ListExportSpec('downtime_list', _export_downtime),
    ]
    return {s.key: s for s in specs}


LIST_EXPORT_REGISTRY: dict[str, ListExportSpec] = _build_registry()


def run_list_export(request: HttpRequest, export_key: str) -> HttpResponse:
    spec = LIST_EXPORT_REGISTRY.get(export_key)
    if not spec:
        from django.http import Http404
        raise Http404(f'Unknown export key: {export_key}')
    return spec.builder(request)
