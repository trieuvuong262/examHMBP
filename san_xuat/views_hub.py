"""Hub Sản xuất — overview, danh sách demo, deep-link redirects."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT

from san_xuat.hub_list import _rows_from_queryset, hub_list_page
from san_xuat.list_filters import (
    SX_FILTER_COST_ORDER,
    SX_FILTER_COST_SHEET,
    SX_FILTER_COST_TYPE,
    SX_FILTER_DISASSEMBLY,
    SX_FILTER_FG_RECEIPT,
    SX_FILTER_MATERIAL_ISSUE,
    SX_FILTER_MO,
    SX_FILTER_NPL_PR,
    SX_FILTER_NPL_SURPLUS,
    SX_FILTER_PACKING,
    SX_FILTER_PLAN_NPL,
    SX_FILTER_PLAN_PERIOD,
    SX_FILTER_PROD_STAT,
    SX_FILTER_PURCHASE_ORDER,
    SX_FILTER_QC_ALERT,
    SX_FILTER_QC_CATALOG,
    SX_FILTER_QC_REQUEST,
    SX_FILTER_QC_SHEET,
    SX_FILTER_SUBCONTRACT,
    SX_FILTER_WIP_HANDOVER,
    SX_FILTER_WIP_RETURN,
    SX_FILTER_WORK_ASSIGN,
    SX_FILTER_WORK_CENTER,
    apply_sx_list_filters,
    default_list_date_range,
    filter_tuple_rows,
    parse_sx_list_filters,
    prepare_hub_list,
    sx_filter_context,
    SxListFilters,
)
from san_xuat.hub_models import (
    SxCostType,
    SxDetailPlan,
    SxDisassemblyOrder,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxMaterialPlan,
    SxNplPurchaseRequest,
    SxNplSurplus,
    SxOrderPlanCost,
    SxOverallPlan,
    SxPackingRecord,
    SxProductionOrder,
    SxProductionStat,
    SxPurchaseOrder,
    SxQcAlert,
    SxQcCriteria,
    SxQcCriteriaGroup,
    SxQcDefect,
    SxQcDefectGroup,
    SxQcInspection,
    SxQcRequest,
    SxQcSamplingMethod,
    SxQcStandardSet,
    SxStandardCostSheet,
    SxSubcontractOrder,
    SxWipHandover,
    SxWipReturn,
    SxWorkAssignment,
    SxWorkCenter,
)
from san_xuat.models import ProcessStep, ProductTechDoc
from san_xuat.views import _perm_ctx
from san_xuat.forms_costing import CostTypeForm, OrderPlanCostCreateForm, StandardCostSheetCreateForm
from san_xuat.forms_plan import (
    DetailPlanExplodeForm,
    ImportKvOrderForm,
    MaterialPlanExplodeForm,
    NplPurchaseRequestCreateForm,
    OverallPlanCreateForm,
    OverallPlanLineForm,
    PurchaseOrderCreateForm,
)
from san_xuat.forms_phase3 import (
    PackingCreateForm,
    PackingLineFormSet,
    SubcontractCreateForm,
    SubcontractMaterialLineForm,
    SubcontractOutLineFormSet,
    SubcontractReceiveForm,
    TraceLookupForm,
    WorkAssignmentCreateForm,
    WorkCenterForm,
)
from san_xuat.forms_dispatch import (
    ScheduleMoUpdateForm,
    DisassemblyCreateForm,
    FgReceiptCreateForm,
    FgReceiptLinkKvForm,
    MaterialIssueApproveForm,
    NplSurplusCreateForm,
    ProductionOrderCreateForm,
    ProductionOrderUpdateForm,
    ProductionStatCreateForm,
    WipHandoverCreateForm,
    WipReturnCreateForm,
)
from san_xuat.forms_qc import (
    QcCriteriaForm,
    QcCriteriaGroupForm,
    QcDefectForm,
    QcDefectGroupForm,
    QcInspectionCreateForm,
    QcInspectionCriteriaLineForm,
    QcInspectionDefectLineFormSet,
    QcInspectionFinalizeForm,
    QcRequestForm,
    QcSamplingMethodForm,
    QcStandardSetForm,
)
from san_xuat.services.dispatch import (
    update_mo_schedule,
    DispatchError,
    approve_material_issue,
    build_material_issue_request,
    confirm_disassembly_order,
    confirm_npl_surplus,
    confirm_stat,
    create_disassembly_order,
    create_fg_receipt_from_mo,
    create_mo_from_bom,
    create_mos_from_detail_plan,
    create_npl_surplus,
    create_production_stat,
    create_wip_handover,
    confirm_wip_handover,
    cancel_wip_return,
    confirm_wip_return,
    create_wip_return,
    reject_wip_handover,
    link_kv_purchase,
    mo_release,
    set_disassembly_lines,
    submit_fg_receipt,
)
from san_xuat.services.costing import list_costing_from_active_boms
from san_xuat.services.costing_export import export_order_plan_cost_xlsx
from san_xuat.services.plan_costing import (
    PlanCostingError,
    build_order_sheet_from_kv,
    build_standard_sheet_from_bom,
    confirm_order_plan_cost,
    confirm_standard_sheet,
    list_active_cost_types,
    update_order_plan_extra_costs,
    update_order_plan_typed_extras,
    upsert_cost_type,
)
from san_xuat.services.planning import (
    PlanningError,
    add_overall_plan_line,
    approve_npl_purchase_request,
    build_overall_lines_from_kv_order,
    build_po_from_purchase_request,
    build_pr_from_material_plan,
    confirm_detail_plan,
    confirm_material_plan,
    confirm_overall_plan,
    confirm_purchase_order,
    create_overall_plan,
    explode_detail_plan_from_overall,
    explode_material_plan,
    link_kv_purchase_to_po,
    reject_npl_purchase_request,
    submit_npl_purchase_request,
)
from san_xuat.services.qc import (
    QcError,
    CriteriaLineInput,
    DefectLineInput,
    acknowledge_alert,
    create_inspection_from_request,
    create_request_from_stat,
    finalize_inspection,
    seed_inspection_criteria_lines,
)

_DEMO_HINT = 'Chưa có dữ liệu demo. Chạy: python manage.py seed_san_xuat_demo'


def _next_code(prefix: str, model, *, field: str = 'code') -> str:
    year = timezone.localdate().year
    base = f'{prefix}-{year}-'
    latest = (
        model.objects.filter(**{f'{field}__startswith': base})
        .order_by('-id')
        .values_list(field, flat=True)
        .first()
    )
    if not latest:
        return f'{base}0001'
    try:
        seq = int(latest.rsplit('-', 1)[-1]) + 1
    except ValueError:
        seq = model.objects.filter(**{f'{field}__startswith': base}).count() + 1
    return f'{base}{seq:04d}'


def _page(request, *, title, subtitle, model, fields, labels, related_url_name=None, order_by='-pk'):
    qs = model.objects.filter(is_demo=True).order_by(order_by)[:100]
    return hub_list_page(
        request,
        perm_ctx=_perm_ctx(request),
        title=title,
        subtitle=subtitle,
        columns=[{'label': label} for label in labels],
        rows=_rows_from_queryset(qs, fields),
        empty_hint=_DEMO_HINT,
        related_url_name=related_url_name,
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def overview(request):
    import json

    from san_xuat.services.overview import build_overview_dashboard, parse_overview_period

    month = (request.GET.get('month') or '').strip()
    date_from_raw = (request.GET.get('date_from') or '').strip()
    date_to_raw = (request.GET.get('date_to') or '').strip()
    product_code = (request.GET.get('product_code') or '').strip()
    team_label = (request.GET.get('team_label') or '').strip()
    active_tab = (request.GET.get('tab') or 'tong-hop').strip().lower()
    allowed_tabs = {'tong-hop', 'lenh-sx', 'san-luong', 'chat-luong', 'dung-chuyen'}
    if active_tab not in allowed_tabs:
        active_tab = 'tong-hop'
    date_from, date_to = parse_overview_period(
        month=month,
        date_from=date_from_raw,
        date_to=date_to_raw,
    )
    dash = build_overview_dashboard(
        date_from=date_from,
        date_to=date_to,
        product_code=product_code,
        team_label=team_label,
    )
    month_value = f'{date_from.year:04d}-{date_from.month:02d}'
    has_filters = bool(
        product_code or team_label
        or month or date_from_raw or date_to_raw
    )

    def _j(obj):
        return json.dumps(obj, ensure_ascii=False)

    return render(request, 'san_xuat/hub_overview.html', {
        **_perm_ctx(request),
        'dash': dash,
        'month_value': month_value,
        'filter_product_code': product_code,
        'filter_team_label': team_label,
        'active_tab': active_tab,
        'has_filters': has_filters,
        'chart_mo_labels_json': _j([row['label'] for row in dash.mo_by_status]),
        'chart_mo_data_json': _j([row['count'] for row in dash.mo_by_status]),
        'chart_day_labels_json': _j([row['label'] for row in dash.production_by_day]),
        'chart_day_good_json': _j([row['qty_good'] for row in dash.production_by_day]),
        'chart_day_defect_json': _j([row['qty_defect'] for row in dash.production_by_day]),
        'chart_qc_data_json': _j([dash.qc_pass, dash.qc_fail, dash.qc_pending]),
        'chart_dt_labels_json': _j([row['reason'][:40] for row in dash.downtime_by_reason]),
        'chart_dt_data_json': _j([row['minutes'] for row in dash.downtime_by_reason]),
        'chart_order_labels_json': _j([row['label'] for row in dash.orders_by_sx_status]),
        'chart_order_data_json': _j([row['count'] for row in dash.orders_by_sx_status]),
        'chart_team_labels_json': _j([row['team_label'] for row in dash.team_output]),
        'chart_team_good_json': _j([row['qty_good'] for row in dash.team_output]),
        'chart_team_defect_json': _j([row['qty_defect'] for row in dash.team_output]),
        'chart_process_labels_json': _j([row['process_name'] for row in dash.process_output]),
        'chart_process_good_json': _j([row['qty_good'] for row in dash.process_output]),
        'chart_process_defect_json': _j([row['qty_defect'] for row in dash.process_output]),
        'chart_product_labels_json': _j([row['product_code'] for row in dash.top_products_output]),
        'chart_product_good_json': _j([row['qty_good'] for row in dash.top_products_output]),
        'chart_product_defect_json': _j([row['qty_defect'] for row in dash.top_products_output]),
        'chart_defect_labels_json': _j([row['product_code'] for row in dash.top_products_defect]),
        'chart_defect_rate_json': _j([row['defect_rate'] for row in dash.top_products_defect]),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_orders(request):
    return redirect('kiotviet:order_lookup')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_npl_stock(request):
    return redirect('kho_npl:material_stock')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_costing(request):
    return render(request, 'san_xuat/hub_costing.html', {**_perm_ctx(request)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
def products_nvl(request):
    """Landing catalog Sản phẩm / NVL (gom lối vào SoT)."""
    from kho_npl.models import Material
    from san_xuat.models import BomVersion, ProductTechDoc

    docs = ProductTechDoc.objects.all()
    kv_count = 0
    try:
        from kiotviet.models import KvProduct
        kv_count = KvProduct.objects.count()
    except Exception:
        pass
    return render(request, 'san_xuat/hub_products_nvl.html', {
        **_perm_ctx(request),
        'doc_total': docs.count(),
        'doc_active': docs.filter(is_active=True).count(),
        'bom_active': BomVersion.objects.filter(status=BomVersion.STATUS_ACTIVE).count(),
        'material_active': Material.objects.filter(is_active=True).count()
        if hasattr(Material, 'is_active') else Material.objects.count(),
        'kv_product_count': kv_count,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_norm(request):
    filters = parse_sx_list_filters(request)
    rows = filter_tuple_rows(list_costing_from_active_boms(), filters)
    return render(request, 'san_xuat/costing_bom_list.html', {
        **_perm_ctx(request),
        'rows': rows,
        'product_count': len(rows),
        **sx_filter_context(filters),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_sheet_list(request):
    base_qs = (
        SxStandardCostSheet.objects.filter(is_demo=False)
        .prefetch_related('lines')
        .order_by('-date_from', '-pk')
    )
    sheets, fctx = prepare_hub_list(request, base_qs, SX_FILTER_COST_SHEET)
    return render(request, 'san_xuat/costing_sheet_list.html', {
        **_perm_ctx(request),
        'sheets': sheets,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def costing_sheet_create(request):
    if request.method == 'POST':
        form = StandardCostSheetCreateForm(request.POST)
        if form.is_valid():
            try:
                sheet = build_standard_sheet_from_bom(
                    name=form.cleaned_data['name'],
                    date_from=form.cleaned_data['date_from'],
                    date_to=form.cleaned_data['date_to'],
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                    product_codes=form.cleaned_data.get('product_code_list'),
                )
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo bảng GT {sheet.code} ({sheet.lines.count()} SP).')
                return redirect('san_xuat:costing_sheet_detail', pk=sheet.pk)
        messages.error(request, 'Không tạo được bảng GT — kiểm tra lại form.')
    else:
        today = timezone.localdate()
        form = StandardCostSheetCreateForm(initial={'date_from': today, 'date_to': today})
    return render(request, 'san_xuat/costing_sheet_form.html', {
        **_perm_ctx(request),
        'form': form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_sheet_detail(request, pk: int):
    sheet = get_object_or_404(
        SxStandardCostSheet.objects.prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and sheet.status == SxStandardCostSheet.STATUS_DRAFT:
            try:
                sheet = confirm_standard_sheet(sheet_id=sheet.pk)
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Bảng GT {sheet.code} đã chốt.')
                return redirect('san_xuat:costing_sheet_detail', pk=sheet.pk)
        elif action == 'refresh' and can_update and sheet.status == SxStandardCostSheet.STATUS_DRAFT:
            try:
                sheet = build_standard_sheet_from_bom(
                    name=sheet.name,
                    date_from=sheet.date_from,
                    date_to=sheet.date_to,
                    notes=sheet.notes,
                    sheet_id=sheet.pk,
                )
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã cập nhật giá thành trên bảng {sheet.code}.')
                return redirect('san_xuat:costing_sheet_detail', pk=sheet.pk)
    return render(request, 'san_xuat/costing_sheet_detail.html', {
        **_perm_ctx(request),
        'sheet': sheet,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_by_order(request):
    base_qs = (
        SxOrderPlanCost.objects.filter(is_demo=False)
        .prefetch_related('lines')
        .order_by('-date_from', '-pk')
    )
    sheets, fctx = prepare_hub_list(request, base_qs, SX_FILTER_COST_ORDER)
    return render(request, 'san_xuat/costing_order_list.html', {
        **_perm_ctx(request),
        'sheets': sheets,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def costing_order_create(request):
    if request.method == 'POST':
        form = OrderPlanCostCreateForm(request.POST)
        if form.is_valid():
            std = form.cleaned_data.get('standard_sheet')
            try:
                sheet = build_order_sheet_from_kv(
                    name=form.cleaned_data['name'],
                    date_from=form.cleaned_data['date_from'],
                    date_to=form.cleaned_data['date_to'],
                    kv_order_kiotviet_id=form.cleaned_data.get('kv_order_kiotviet_id'),
                    kv_order_code=form.cleaned_data.get('kv_order_code') or '',
                    standard_sheet_id=std.pk if std else None,
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f'Đã tạo GTKH {sheet.code} — tổng {sheet.total_cost} ({sheet.lines.count()} dòng).',
                )
                return redirect('san_xuat:costing_order_detail', pk=sheet.pk)
        messages.error(request, 'Không tạo được GTKH — kiểm tra lại form.')
    else:
        today = timezone.localdate()
        form = OrderPlanCostCreateForm(initial={'date_from': today, 'date_to': today})
    return render(request, 'san_xuat/costing_order_form.html', {
        **_perm_ctx(request),
        'form': form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_order_detail(request, pk: int):
    sheet = get_object_or_404(
        SxOrderPlanCost.objects.prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and sheet.status == SxOrderPlanCost.STATUS_DRAFT:
            try:
                sheet = confirm_order_plan_cost(sheet_id=sheet.pk)
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'GTKH {sheet.code} đã chốt.')
                return redirect('san_xuat:costing_order_detail', pk=sheet.pk)
        elif action == 'refresh' and can_update and sheet.status == SxOrderPlanCost.STATUS_DRAFT:
            try:
                sheet = build_order_sheet_from_kv(
                    name=sheet.name,
                    date_from=sheet.date_from,
                    date_to=sheet.date_to,
                    kv_order_kiotviet_id=sheet.kv_order_kiotviet_id,
                    kv_order_code=sheet.kv_order_code,
                    sheet_id=sheet.pk,
                )
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã cập nhật GTKH {sheet.code}.')
                return redirect('san_xuat:costing_order_detail', pk=sheet.pk)
        elif action == 'save_extras' and can_update and sheet.status == SxOrderPlanCost.STATUS_DRAFT:
            cost_types = list_active_cost_types()
            typed: dict[int, dict[int, Decimal]] = {}
            for line in sheet.lines.all():
                typed[line.pk] = {}
                for ct in cost_types:
                    raw = (request.POST.get(f'extra_{line.pk}_{ct.pk}') or '').strip()
                    if raw:
                        try:
                            typed[line.pk][ct.pk] = Decimal(raw)
                        except Exception:
                            messages.error(
                                request,
                                f'Chi phí thêm không hợp lệ: {line.product_code} / {ct.code}.',
                            )
                            return redirect('san_xuat:costing_order_detail', pk=sheet.pk)
                    else:
                        typed[line.pk][ct.pk] = Decimal('0')
            try:
                sheet = update_order_plan_typed_extras(sheet_id=sheet.pk, extras=typed)
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã cập nhật chi phí thêm — tổng {sheet.total_cost}.')
                return redirect('san_xuat:costing_order_detail', pk=sheet.pk)
    cost_types = list_active_cost_types()
    line_rows = []
    for line in sheet.lines.prefetch_related('typed_extras').all():
        amap = {ex.cost_type_id: ex.amount for ex in line.typed_extras.all()}
        cells = [
            {'ct': ct, 'amount': amap.get(ct.pk, Decimal('0'))}
            for ct in cost_types
        ]
        line_rows.append({'line': line, 'cells': cells})
    return render(request, 'san_xuat/costing_order_detail.html', {
        **_perm_ctx(request),
        'sheet': sheet,
        'can_update': can_update,
        'cost_types': cost_types,
        'line_rows': line_rows,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_order_export(request, pk: int):
    sheet = get_object_or_404(
        SxOrderPlanCost.objects.prefetch_related('lines__typed_extras__cost_type'),
        pk=pk,
    )
    return export_order_plan_cost_xlsx(sheet=sheet)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_cost_types(request):
    base_qs = SxCostType.objects.filter(is_demo=False).order_by('sort_order', 'code')
    cost_types, fctx = prepare_hub_list(request, base_qs, SX_FILTER_COST_TYPE)
    return render(request, 'san_xuat/costing_cost_type_list.html', {
        **_perm_ctx(request),
        'cost_types': cost_types,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def costing_cost_type_create(request):
    if request.method == 'POST':
        form = CostTypeForm(request.POST)
        if form.is_valid():
            try:
                ct = upsert_cost_type(
                    code=form.cleaned_data['code'],
                    name=form.cleaned_data['name'],
                    sort_order=form.cleaned_data.get('sort_order') or 100,
                    is_active=form.cleaned_data.get('is_active', True),
                    notes=form.cleaned_data.get('notes') or '',
                )
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo loại CP {ct.code}.')
                return redirect('san_xuat:costing_cost_types')
        messages.error(request, 'Không tạo được loại CP — kiểm tra lại form.')
    else:
        form = CostTypeForm(initial={'sort_order': 100, 'is_active': True})
    return render(request, 'san_xuat/costing_cost_type_form.html', {
        **_perm_ctx(request),
        'form': form,
        'title': 'Thêm loại chi phí',
    })


@module_perm_required(MODULE_SAN_XUAT, 'edit')
def costing_cost_type_edit(request, pk: int):
    ct = get_object_or_404(SxCostType, pk=pk, is_demo=False)
    if request.method == 'POST':
        form = CostTypeForm(request.POST)
        if form.is_valid():
            try:
                ct = upsert_cost_type(
                    code=form.cleaned_data['code'],
                    name=form.cleaned_data['name'],
                    sort_order=form.cleaned_data.get('sort_order') or 100,
                    is_active=bool(form.cleaned_data.get('is_active')),
                    notes=form.cleaned_data.get('notes') or '',
                    cost_type_id=ct.pk,
                )
            except PlanCostingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã cập nhật loại CP {ct.code}.')
                return redirect('san_xuat:costing_cost_types')
        messages.error(request, 'Không lưu được loại CP.')
    else:
        form = CostTypeForm(initial={
            'code': ct.code,
            'name': ct.name,
            'sort_order': ct.sort_order,
            'is_active': ct.is_active,
            'notes': ct.notes,
        })
    return render(request, 'san_xuat/costing_cost_type_form.html', {
        **_perm_ctx(request),
        'form': form,
        'title': f'Sửa {ct.code}',
        'cost_type': ct,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_stub(request):
    return render(request, 'san_xuat/hub_plan.html', {**_perm_ctx(request)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall(request):
    base_qs = (
        SxOverallPlan.objects.filter(is_demo=False)
        .prefetch_related('lines')
        .order_by('-date_from', '-pk')
    )
    plans, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PLAN_PERIOD)
    return render(request, 'san_xuat/plan_overall_list.html', {
        **_perm_ctx(request),
        'plans': plans,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def plan_overall_create(request):
    if request.method == 'POST':
        form = OverallPlanCreateForm(request.POST)
        if form.is_valid():
            try:
                plan = create_overall_plan(
                    name=form.cleaned_data['name'],
                    date_from=form.cleaned_data['date_from'],
                    date_to=form.cleaned_data['date_to'],
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo KHTT {plan.code}.')
                return redirect('san_xuat:plan_overall_detail', pk=plan.pk)
        messages.error(request, 'Không tạo được KHTT — kiểm tra lại form.')
    else:
        today = timezone.localdate()
        form = OverallPlanCreateForm(initial={'date_from': today, 'date_to': today})
    return render(request, 'san_xuat/plan_overall_form.html', {
        **_perm_ctx(request),
        'form': form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall_detail(request, pk: int):
    plan = get_object_or_404(
        SxOverallPlan.objects.prefetch_related('lines', 'material_plans', 'detail_plans'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    line_form = OverallPlanLineForm()
    import_form = ImportKvOrderForm()

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'add_line' and can_update and plan.status == SxOverallPlan.STATUS_DRAFT:
            line_form = OverallPlanLineForm(request.POST)
            if line_form.is_valid():
                try:
                    add_overall_plan_line(
                        plan_id=plan.pk,
                        product_code=line_form.cleaned_data['product_code'],
                        qty_planned=line_form.cleaned_data['qty_planned'],
                        qty_required=line_form.cleaned_data.get('qty_required'),
                        product_name=line_form.cleaned_data.get('product_name') or '',
                        capacity_per_day=line_form.cleaned_data.get('capacity_per_day') or Decimal('0'),
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, 'Đã thêm dòng SP.')
                    return redirect('san_xuat:plan_overall_detail', pk=plan.pk)
            messages.error(request, 'Không thêm được dòng — kiểm tra lại form.')

        elif action == 'import_kv' and can_update and plan.status == SxOverallPlan.STATUS_DRAFT:
            import_form = ImportKvOrderForm(request.POST)
            if import_form.is_valid():
                try:
                    created = build_overall_lines_from_kv_order(
                        plan_id=plan.pk,
                        kv_order_kiotviet_id=import_form.cleaned_data.get('kv_order_kiotviet_id'),
                        kv_order_code=import_form.cleaned_data.get('kv_order_code') or '',
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã import {len(created)} dòng từ đơn KV.')
                    return redirect('san_xuat:plan_overall_detail', pk=plan.pk)
            messages.error(request, 'Không import được đơn KV.')

        elif action == 'confirm' and can_update and plan.status == SxOverallPlan.STATUS_DRAFT:
            try:
                plan = confirm_overall_plan(plan_id=plan.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'KHTT {plan.code} đã xác nhận.')
                return redirect('san_xuat:plan_overall_detail', pk=plan.pk)

    material_plans = plan.material_plans.filter(is_demo=False).order_by('-created_at')
    detail_plans = plan.detail_plans.filter(is_demo=False).order_by('-created_at')
    return render(request, 'san_xuat/plan_overall_detail.html', {
        **_perm_ctx(request),
        'plan': plan,
        'can_update': can_update,
        'line_form': line_form,
        'import_form': import_form,
        'material_plans': material_plans,
        'detail_plans': detail_plans,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail(request):
    base_qs = (
        SxDetailPlan.objects.filter(is_demo=False)
        .select_related('overall_plan')
        .prefetch_related('lines')
        .order_by('-date_from', '-pk')
    )
    plans, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PLAN_PERIOD)
    return render(request, 'san_xuat/plan_detail_list.html', {
        **_perm_ctx(request),
        'plans': plans,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def plan_detail_create(request):
    overall = None
    if request.method == 'POST':
        form = DetailPlanExplodeForm(request.POST)
        if form.is_valid():
            overall = form.cleaned_data['overall_plan']
            try:
                detail = explode_detail_plan_from_overall(
                    overall_plan_id=overall.pk,
                    code=form.cleaned_data.get('code') or None,
                    name=form.cleaned_data.get('name') or '',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f'Đã lập KHCT {detail.code} ({detail.lines.count()} dòng theo ngày).',
                )
                return redirect('san_xuat:plan_detail_detail', pk=detail.pk)
        messages.error(request, 'Không tạo được KHCT — kiểm tra lại form.')
    else:
        initial = {}
        overall_id = request.GET.get('overall')
        if overall_id and str(overall_id).isdigit():
            overall = get_object_or_404(SxOverallPlan, pk=int(overall_id))
            initial['overall_plan'] = overall.pk
        form = DetailPlanExplodeForm(initial=initial)
    return render(request, 'san_xuat/plan_detail_form.html', {
        **_perm_ctx(request),
        'form': form,
        'overall': overall,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail_detail(request, pk: int):
    from collections import defaultdict
    from datetime import timedelta

    detail = get_object_or_404(
        SxDetailPlan.objects.select_related('overall_plan')
        .prefetch_related('lines', 'production_orders'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and detail.status == SxOverallPlan.STATUS_DRAFT:
            try:
                detail = confirm_detail_plan(plan_id=detail.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'KHCT {detail.code} đã xác nhận.')
                return redirect('san_xuat:plan_detail_detail', pk=detail.pk)
        elif action == 'refresh' and can_update:
            if not detail.overall_plan_id:
                messages.error(request, 'KHCT không gắn KHTT nguồn.')
            else:
                try:
                    detail = explode_detail_plan_from_overall(overall_plan_id=detail.overall_plan_id)
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã cập nhật phân bổ ngày cho KHCT {detail.code}.')
                    return redirect('san_xuat:plan_detail_detail', pk=detail.pk)
        elif action == 'generate_mos' and can_update and detail.status == SxOverallPlan.STATUS_CONFIRMED:
            try:
                created = create_mos_from_detail_plan(detail_plan_id=detail.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                if created:
                    messages.success(request, f'Đã tạo {len(created)} LSX từ KHCT {detail.code}.')
                else:
                    messages.info(request, 'Không có LSX mới — các dòng đã có LSX tương ứng.')
                return redirect('san_xuat:plan_detail_detail', pk=detail.pk)

    dates: list = []
    day = detail.date_from
    while day <= detail.date_to:
        dates.append(day)
        day += timedelta(days=1)

    products: dict[str, str] = {}
    grid: dict[str, dict] = defaultdict(dict)
    for line in detail.lines.all():
        products[line.product_code] = line.product_name
        grid[line.product_code][line.plan_date] = line.qty

    product_rows = []
    for code in sorted(products.keys()):
        cells = []
        row_total = Decimal('0')
        for plan_date in dates:
            qty = grid[code].get(plan_date, Decimal('0'))
            row_total += qty
            cells.append({'date': plan_date, 'qty': qty})
        product_rows.append({
            'code': code,
            'name': products[code],
            'cells': cells,
            'total': row_total,
        })

    date_totals = []
    for plan_date in dates:
        total = sum((grid[code].get(plan_date, Decimal('0')) for code in products), Decimal('0'))
        date_totals.append({'date': plan_date, 'total': total})

    production_orders = detail.production_orders.filter(is_demo=False).order_by('planned_start', 'code')
    return render(request, 'san_xuat/plan_detail_detail.html', {
        **_perm_ctx(request),
        'detail_plan': detail,
        'can_update': can_update,
        'dates': dates,
        'product_rows': product_rows,
        'date_totals': date_totals,
        'production_orders': production_orders,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_npl(request):
    base_qs = (
        SxMaterialPlan.objects.filter(is_demo=False)
        .select_related('overall_plan')
        .prefetch_related('lines')
        .order_by('-created_at', '-pk')
    )
    plans, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PLAN_NPL)
    return render(request, 'san_xuat/plan_npl_list.html', {
        **_perm_ctx(request),
        'plans': plans,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def plan_npl_create(request):
    overall = None
    if request.method == 'POST':
        form = MaterialPlanExplodeForm(request.POST)
        if form.is_valid():
            overall = form.cleaned_data['overall_plan']
            try:
                mat_plan = explode_material_plan(
                    overall_plan_id=overall.pk,
                    code=form.cleaned_data.get('code') or None,
                    name=form.cleaned_data.get('name') or '',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tính KHNVL {mat_plan.code} ({mat_plan.lines.count()} dòng NVL).')
                return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
        messages.error(request, 'Không tạo được KHNVL — kiểm tra lại form.')
    else:
        initial = {}
        overall_id = request.GET.get('overall')
        if overall_id and str(overall_id).isdigit():
            overall = get_object_or_404(SxOverallPlan, pk=int(overall_id))
            initial['overall_plan'] = overall.pk
        form = MaterialPlanExplodeForm(initial=initial)
    return render(request, 'san_xuat/plan_npl_form.html', {
        **_perm_ctx(request),
        'form': form,
        'overall': overall,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_npl_detail(request, pk: int):
    mat_plan = get_object_or_404(
        SxMaterialPlan.objects.select_related('overall_plan').prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and mat_plan.status == SxOverallPlan.STATUS_DRAFT:
            try:
                mat_plan = confirm_material_plan(plan_id=mat_plan.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'KHNVL {mat_plan.code} đã xác nhận.')
                return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
        elif action == 'refresh' and can_update:
            if not mat_plan.overall_plan_id:
                messages.error(request, 'KHNVL không gắn KHTT nguồn.')
            else:
                try:
                    mat_plan = explode_material_plan(overall_plan_id=mat_plan.overall_plan_id)
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã cập nhật tồn/shortfall cho KHNVL {mat_plan.code}.')
                    return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
    shortfall_total = sum((line.qty_shortfall or 0 for line in mat_plan.lines.all()), Decimal('0'))
    purchase_requests = mat_plan.purchase_requests.filter(is_demo=False).order_by('-created_at')
    return render(request, 'san_xuat/plan_npl_detail.html', {
        **_perm_ctx(request),
        'mat_plan': mat_plan,
        'can_update': can_update,
        'shortfall_total': shortfall_total,
        'purchase_requests': purchase_requests,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_purchase_request(request):
    base_qs = (
        SxNplPurchaseRequest.objects.filter(is_demo=False)
        .select_related('material_plan', 'material_plan__overall_plan')
        .prefetch_related('lines')
        .order_by('-created_at', '-pk')
    )
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_NPL_PR)
    return render(request, 'san_xuat/npl_purchase_request_list.html', {
        **_perm_ctx(request),
        'requests': requests_qs,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def npl_purchase_request_create(request):
    mat_plan = None
    if request.method == 'POST':
        form = NplPurchaseRequestCreateForm(request.POST)
        if form.is_valid():
            try:
                pr = build_pr_from_material_plan(
                    material_plan_id=form.cleaned_data['material_plan'].pk,
                    only_shortfall=form.cleaned_data.get('only_shortfall', True),
                    code=form.cleaned_data.get('code') or None,
                    due_date=form.cleaned_data.get('due_date'),
                    notes=form.cleaned_data.get('notes') or '',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo YCM {pr.code} ({pr.lines.count()} dòng NVL).')
                return redirect('san_xuat:npl_purchase_request_detail', pk=pr.pk)
        messages.error(request, 'Không tạo được YCM — kiểm tra lại form.')
    else:
        initial = {'only_shortfall': True}
        plan_id = request.GET.get('plan')
        if plan_id and str(plan_id).isdigit():
            mat_plan = get_object_or_404(SxMaterialPlan, pk=int(plan_id))
            initial['material_plan'] = mat_plan.pk
        form = NplPurchaseRequestCreateForm(initial=initial)
    return render(request, 'san_xuat/npl_purchase_request_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mat_plan': mat_plan,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_purchase_request_detail(request, pk: int):
    pr = get_object_or_404(
        SxNplPurchaseRequest.objects.select_related('material_plan', 'material_plan__overall_plan')
        .prefetch_related('lines', 'purchase_orders'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'submit' and can_update and pr.status == SxNplPurchaseRequest.STATUS_DRAFT:
            try:
                pr = submit_npl_purchase_request(request_id=pr.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'YCM {pr.code} đã gửi duyệt.')
                return redirect('san_xuat:npl_purchase_request_detail', pk=pr.pk)
        elif action == 'approve' and can_update and pr.status == SxNplPurchaseRequest.STATUS_SUBMITTED:
            try:
                pr = approve_npl_purchase_request(request_id=pr.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'YCM {pr.code} đã duyệt.')
                return redirect('san_xuat:npl_purchase_request_detail', pk=pr.pk)
        elif action == 'reject' and can_update and pr.status == SxNplPurchaseRequest.STATUS_SUBMITTED:
            try:
                pr = reject_npl_purchase_request(
                    request_id=pr.pk,
                    notes=(request.POST.get('reject_notes') or '').strip(),
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'YCM {pr.code} đã từ chối.')
                return redirect('san_xuat:npl_purchase_request_detail', pk=pr.pk)
    purchase_orders = pr.purchase_orders.filter(is_demo=False).order_by('-created_at')
    return render(request, 'san_xuat/npl_purchase_request_detail.html', {
        **_perm_ctx(request),
        'pr': pr,
        'can_update': can_update,
        'purchase_orders': purchase_orders,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def purchase_order(request):
    base_qs = (
        SxPurchaseOrder.objects.filter(is_demo=False)
        .select_related('purchase_request', 'purchase_request__material_plan')
        .prefetch_related('lines')
        .order_by('-created_at', '-pk')
    )
    orders, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PURCHASE_ORDER)
    return render(request, 'san_xuat/purchase_order_list.html', {
        **_perm_ctx(request),
        'orders': orders,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def purchase_order_create(request):
    pr = None
    if request.method == 'POST':
        form = PurchaseOrderCreateForm(request.POST)
        if form.is_valid():
            pr = form.cleaned_data['purchase_request']
            try:
                po = build_po_from_purchase_request(
                    purchase_request_id=pr.pk,
                    supplier_name=form.cleaned_data.get('supplier_name') or '',
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo DMH {po.code} ({po.lines.count()} dòng NVL).')
                return redirect('san_xuat:purchase_order_detail', pk=po.pk)
        messages.error(request, 'Không tạo được DMH — kiểm tra lại form.')
    else:
        initial = {}
        pr_id = request.GET.get('pr')
        if pr_id and str(pr_id).isdigit():
            pr = get_object_or_404(SxNplPurchaseRequest, pk=int(pr_id))
            initial['purchase_request'] = pr.pk
        form = PurchaseOrderCreateForm(initial=initial)
    return render(request, 'san_xuat/purchase_order_form.html', {
        **_perm_ctx(request),
        'form': form,
        'pr': pr,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def purchase_order_detail(request, pk: int):
    po = get_object_or_404(
        SxPurchaseOrder.objects.select_related(
            'purchase_request',
            'purchase_request__material_plan',
        ).prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    link_form = FgReceiptLinkKvForm()
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and po.status == SxPurchaseOrder.STATUS_DRAFT:
            try:
                po = confirm_purchase_order(order_id=po.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'DMH {po.code} đã xác nhận.')
                return redirect('san_xuat:purchase_order_detail', pk=po.pk)
        elif action == 'link_kv' and can_update and not po.kv_purchase_kiotviet_id:
            link_form = FgReceiptLinkKvForm(request.POST)
            if link_form.is_valid():
                try:
                    po = link_kv_purchase_to_po(
                        order_id=po.pk,
                        kv_purchase_kiotviet_id=link_form.cleaned_data.get('kv_purchase_kiotviet_id'),
                        kv_purchase_code=link_form.cleaned_data.get('kv_purchase_code') or '',
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã liên kết phiếu nhập KV {po.kv_purchase_code}.')
                    return redirect('san_xuat:purchase_order_detail', pk=po.pk)
            messages.error(request, 'Không liên kết được phiếu nhập KV.')
    return render(request, 'san_xuat/purchase_order_detail.html', {
        **_perm_ctx(request),
        'po': po,
        'can_update': can_update,
        'link_form': link_form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_stub(request):
    from san_xuat.services.mo_progress import pending_material_issue_qs

    pending_ycx = pending_material_issue_qs().count()
    return render(request, 'san_xuat/hub_dispatch.html', {
        **_perm_ctx(request),
        'pending_ycx_count': pending_ycx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo(request):
    base_qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .order_by('-order_date', '-pk')
        .select_related('bom_version')
    )
    orders, fctx = prepare_hub_list(request, base_qs, SX_FILTER_MO)
    return render(request, 'san_xuat/dispatch_mo_list.html', {
        **_perm_ctx(request),
        'page_title': 'Lệnh sản xuất',
        'orders': orders,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_mo_create(request):
    if request.method == 'POST':
        form = ProductionOrderCreateForm(request.POST)
        if form.is_valid():
            try:
                mo = create_mo_from_bom(
                    product_code=form.cleaned_data['product_code'],
                    qty=form.cleaned_data['qty'],
                    code=form.cleaned_data.get('code') or None,
                    order_date=form.cleaned_data.get('order_date') or timezone.localdate(),
                    due_date=form.cleaned_data.get('due_date'),
                    planned_start=form.cleaned_data.get('planned_start'),
                    planned_end=form.cleaned_data.get('planned_end'),
                    team_label=form.cleaned_data.get('team_label') or '',
                    notes=form.cleaned_data.get('notes') or '',
                    user=request.user,
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo lệnh sản xuất {mo.code}.')
                return redirect('san_xuat:dispatch_mo_detail', pk=mo.pk)
        else:
            messages.error(request, 'Không tạo được lệnh sản xuất — kiểm tra lại form.')
    else:
        form = ProductionOrderCreateForm(initial={'order_date': timezone.localdate()})
    return render(request, 'san_xuat/dispatch_mo_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mode': 'create',
    })


WIZARD_STEPS = [
    (1, 'Tạo lệnh'),
    (2, 'Phát hành'),
    (3, 'Xuất vật tư'),
    (4, 'Duyệt xuất kho'),
    (5, 'Thống kê sản xuất'),
    (6, 'Kiểm tra chất lượng'),
    (7, 'Nhập thành phẩm & đóng gói'),
]


def _wizard_step_for_mo(mo) -> int:
    from san_xuat.services.mo_progress import build_mo_progress

    progress = build_mo_progress(mo)
    for step in progress.steps:
        if step.done:
            continue
        if step.key == 'created':
            return 1
        if step.key == 'released':
            return 2
        if step.key == 'issue':
            has_ycx = mo.material_issue_requests.filter(is_demo=False).exists()
            return 4 if has_ycx else 3
        if step.key == 'stat':
            return 5
        if step.key == 'qc':
            return 6
        if step.key in ('fg', 'packing'):
            return 7
    return 7


@module_perm_required(MODULE_SAN_XUAT, 'view')
def run_order_wizard(request, mo_id: int | None = None):
    """Wizard «Chạy lệnh mới» — 7 bước có thanh tiến độ."""
    from san_xuat.services.mo_progress import build_mo_progress, pending_material_issue_qs

    mo = None
    if mo_id:
        mo = get_object_or_404(SxProductionOrder, pk=mo_id, is_demo=False)

    step_param = request.GET.get('step') or request.POST.get('step')
    try:
        step = int(step_param) if step_param else (_wizard_step_for_mo(mo) if mo else 1)
    except (TypeError, ValueError):
        step = 1
    step = max(1, min(7, step))

    can = _perm_ctx(request)
    can_update = can.get('can_update')
    create_form = ProductionOrderCreateForm(initial={'order_date': timezone.localdate()})
    stat_form = None

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'create_mo' and can.get('can_create'):
            create_form = ProductionOrderCreateForm(request.POST)
            if create_form.is_valid():
                try:
                    mo = create_mo_from_bom(
                        product_code=create_form.cleaned_data['product_code'],
                        qty=create_form.cleaned_data['qty'],
                        code=create_form.cleaned_data.get('code') or None,
                        order_date=create_form.cleaned_data.get('order_date') or timezone.localdate(),
                        due_date=create_form.cleaned_data.get('due_date'),
                        planned_start=create_form.cleaned_data.get('planned_start'),
                        planned_end=create_form.cleaned_data.get('planned_end'),
                        team_label=create_form.cleaned_data.get('team_label') or '',
                        notes=create_form.cleaned_data.get('notes') or '',
                        user=request.user,
                    )
                except DispatchError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã tạo lệnh {mo.code}. Tiếp tục phát hành.')
                    return redirect(f"{reverse('san_xuat:run_order_wizard_mo', kwargs={'mo_id': mo.pk})}?step=2")
            else:
                messages.error(request, 'Không tạo được lệnh — kiểm tra form.')
                step = 1

        elif mo and action == 'release' and can_update:
            try:
                mo_release(mo_id=mo.pk, user=request.user)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã phát hành {mo.code}.')
                return redirect(f"{reverse('san_xuat:run_order_wizard_mo', kwargs={'mo_id': mo.pk})}?step=3")

        elif mo and action == 'create_ycx' and can_update:
            try:
                req = build_material_issue_request(
                    production_order_id=mo.pk, user=request.user, notes='Từ wizard chạy lệnh',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo yêu cầu xuất {req.code}. Chuyển kho duyệt.')
                return redirect(f"{reverse('san_xuat:run_order_wizard_mo', kwargs={'mo_id': mo.pk})}?step=4")

        elif mo and action == 'create_stat' and can.get('can_create'):
            stat_form = ProductionStatCreateForm(request.POST)
            if stat_form.is_valid():
                try:
                    st = create_production_stat(
                        production_order_id=mo.pk,
                        stat_date=stat_form.cleaned_data.get('stat_date') or timezone.localdate(),
                        process_name=stat_form.cleaned_data.get('process_name') or '',
                        qty_good=stat_form.cleaned_data.get('qty_good') or Decimal('0'),
                        qty_defect=stat_form.cleaned_data.get('qty_defect') or Decimal('0'),
                        team_label=stat_form.cleaned_data.get('team_label') or mo.team_label or '',
                        notes=stat_form.cleaned_data.get('notes') or '',
                    )
                    from san_xuat.services.gates import check_issue_before_stat
                    gate = check_issue_before_stat(mo=mo)
                    if gate.should_warn:
                        messages.warning(request, gate.message)
                    st = confirm_stat(stat_id=st.pk)
                except DispatchError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã ghi và xác nhận thống kê {st.code}.')
                    return redirect(f"{reverse('san_xuat:run_order_wizard_mo', kwargs={'mo_id': mo.pk})}?step=6")
            else:
                messages.error(request, 'Không tạo được thống kê — kiểm tra form.')
                step = 5

        elif mo and action == 'create_ycntp' and can_update:
            from san_xuat.services.gates import (
                check_open_qc_alert_before_fg,
                check_qc_pass_before_fg,
                check_stat_before_fg,
            )

            for gate in (
                check_stat_before_fg(mo=mo),
                check_open_qc_alert_before_fg(mo=mo),
                check_qc_pass_before_fg(mo=mo),
            ):
                if gate.should_warn:
                    messages.warning(request, gate.message)
            try:
                fg = create_fg_receipt_from_mo(production_order_id=mo.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo yêu cầu nhập thành phẩm {fg.code}.')
                return redirect('san_xuat:dispatch_fg_receipt_req_detail', pk=fg.pk)

    if mo and not mo_id:
        return redirect('san_xuat:run_order_wizard_mo', mo_id=mo.pk)

    progress = build_mo_progress(mo) if mo else None
    latest_ycx = None
    if mo:
        latest_ycx = (
            mo.material_issue_requests.filter(is_demo=False)
            .select_related('stock_issue')
            .order_by('-pk')
            .first()
        )
        if step == 5 and stat_form is None:
            stat_form = ProductionStatCreateForm(initial={
                'stat_date': timezone.localdate(),
                'team_label': mo.team_label or '',
                'qty_good': mo.qty,
            })

    return render(request, 'san_xuat/run_order_wizard.html', {
        **can,
        'mo': mo,
        'step': step,
        'steps': WIZARD_STEPS,
        'progress': progress,
        'create_form': create_form,
        'stat_form': stat_form,
        'latest_ycx': latest_ycx,
        'pending_ycx_count': pending_material_issue_qs().count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo_detail(request, pk: int):
    mo = (
        SxProductionOrder.objects.select_related('bom_version__tech_doc')
        .prefetch_related('bom_version__lines__material')
        .get(pk=pk)
    )
    can_update = _perm_ctx(request).get('can_update')

    # Handle actions
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'save' and mo.status == SxProductionOrder.STATUS_DRAFT and can_update:
            form = ProductionOrderUpdateForm(request.POST)
            if form.is_valid():
                mo.qty = form.cleaned_data['qty']
                mo.due_date = form.cleaned_data.get('due_date')
                mo.planned_start = form.cleaned_data.get('planned_start')
                mo.planned_end = form.cleaned_data.get('planned_end')
                mo.team_label = form.cleaned_data.get('team_label') or ''
                mo.notes = form.cleaned_data.get('notes') or ''
                mo.save()
                messages.success(request, 'Đã lưu LSX.')
                return redirect('san_xuat:dispatch_mo_detail', pk=mo.pk)
            messages.error(request, 'Không lưu được LSX — kiểm tra lại form.')

        elif action == 'release' and mo.status == SxProductionOrder.STATUS_DRAFT and can_update:
            try:
                mo_release(mo_id=mo.pk, user=request.user)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Lệnh sản xuất {mo.code} đã phát hành.')
                return redirect('san_xuat:dispatch_mo_detail', pk=mo.pk)

        elif action == 'create_ycx' and mo.status in (
            SxProductionOrder.STATUS_RELEASED,
            SxProductionOrder.STATUS_IN_PROGRESS,
            SxProductionOrder.STATUS_DONE,
        ):
            try:
                req = build_material_issue_request(
                    production_order_id=mo.pk,
                    user=request.user,
                    notes='',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo yêu cầu xuất vật tư {req.code}.')
                return redirect('san_xuat:dispatch_material_issue_req_detail', pk=req.pk)

        elif action == 'create_ycntp' and mo.status in (
            SxProductionOrder.STATUS_IN_PROGRESS,
            SxProductionOrder.STATUS_DONE,
        ):
            from san_xuat.services.gates import (
                check_open_qc_alert_before_fg,
                check_qc_pass_before_fg,
                check_stat_before_fg,
            )

            for gate in (
                check_stat_before_fg(mo=mo),
                check_open_qc_alert_before_fg(mo=mo),
                check_qc_pass_before_fg(mo=mo),
            ):
                if gate.should_warn:
                    messages.warning(request, gate.message)
            try:
                fg_req = create_fg_receipt_from_mo(production_order_id=mo.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo yêu cầu nhập thành phẩm {fg_req.code}.')
                return redirect('san_xuat:dispatch_fg_receipt_req_detail', pk=fg_req.pk)

    update_form = ProductionOrderUpdateForm(initial={
        'qty': mo.qty,
        'due_date': mo.due_date,
        'planned_start': mo.planned_start,
        'planned_end': mo.planned_end,
        'team_label': mo.team_label,
        'notes': mo.notes,
    })

    ycx_list = (
        mo.material_issue_requests.select_related('stock_issue')
        .all()
        .order_by('-request_date', '-pk')[:50]
    )
    stats_list = mo.production_stats.all().order_by('-stat_date', '-pk')[:50]
    qc_alerts = (
        mo.qc_alerts.filter(is_demo=False)
        .select_related('production_stat', 'qc_inspection')
        .order_by('-created_at')[:20]
    )
    fg_receipt_list = (
        mo.fg_receipt_requests.filter(is_demo=False)
        .select_related('production_stat')
        .order_by('-request_date', '-pk')[:20]
    )
    wip_handover_list = (
        mo.wip_handovers.filter(is_demo=False)
        .order_by('-handover_date', '-pk')[:20]
    )

    bom_lines = []
    if mo.bom_version_id:
        for bl in mo.bom_version.lines.all():
            qty_per_unit = bl.qty_with_scrap
            qty_total = qty_per_unit * (mo.qty or 0)
            bom_lines.append({
                'material_code': bl.material.code,
                'material_name': bl.material.name,
                'qty_per_unit': qty_per_unit,
                'qty_total': qty_total,
                'scrap_pct': bl.scrap_pct,
            })

    from san_xuat.services.mo_progress import build_mo_progress

    progress = build_mo_progress(mo)

    return render(request, 'san_xuat/dispatch_mo_detail.html', {
        **_perm_ctx(request),
        'mo': mo,
        'update_form': update_form,
        'can_update': can_update,
        'ycx_list': ycx_list,
        'stats_list': stats_list,
        'qc_alerts': qc_alerts,
        'fg_receipt_list': fg_receipt_list,
        'wip_handover_list': wip_handover_list,
        'bom_lines': bom_lines,
        'progress': progress,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_disassembly(request):
    base_qs = (
        SxDisassemblyOrder.objects.filter(is_demo=False)
        .select_related('production_order')
        .order_by('-order_date', '-pk')
    )
    orders, fctx = prepare_hub_list(request, base_qs, SX_FILTER_DISASSEMBLY)
    return render(request, 'san_xuat/disassembly_list.html', {
        **_perm_ctx(request),
        'orders': orders,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_disassembly_create(request):
    if request.method == 'POST':
        form = DisassemblyCreateForm(request.POST)
        if form.is_valid():
            mo = form.cleaned_data.get('production_order')
            try:
                order = create_disassembly_order(
                    product_code=form.cleaned_data['product_code'],
                    product_name=form.cleaned_data.get('product_name') or '',
                    qty=form.cleaned_data['qty'],
                    order_date=form.cleaned_data.get('order_date'),
                    production_order_id=mo.pk if mo else None,
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                    lines=[{
                        'material_code': form.cleaned_data['material_code'],
                        'qty': form.cleaned_data['material_qty'],
                    }],
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo LTD {order.code}.')
                return redirect('san_xuat:dispatch_disassembly_detail', pk=order.pk)
        messages.error(request, 'Không tạo được LTD — kiểm tra lại form.')
    else:
        form = DisassemblyCreateForm(initial={'order_date': timezone.localdate()})
    return render(request, 'san_xuat/disassembly_form.html', {
        **_perm_ctx(request),
        'form': form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_disassembly_detail(request, pk: int):
    order = get_object_or_404(
        SxDisassemblyOrder.objects.select_related('production_order').prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and order.status == SxDisassemblyOrder.STATUS_DRAFT:
            try:
                order = confirm_disassembly_order(order_id=order.pk, create_surplus=True)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f'Đã xác nhận {order.code} — đã sinh phiếu NPL thừa nháp từ dòng thu hồi.',
                )
                return redirect('san_xuat:dispatch_disassembly_detail', pk=order.pk)
        elif action == 'add_line' and order.status == SxDisassemblyOrder.STATUS_DRAFT:
            mat_code = (request.POST.get('material_code') or '').strip()
            raw_qty = (request.POST.get('material_qty') or '').strip()
            try:
                mat_qty = Decimal(raw_qty)
            except Exception:
                messages.error(request, 'SL thu hồi không hợp lệ.')
                return redirect('san_xuat:dispatch_disassembly_detail', pk=order.pk)
            existing = [
                {'material_code': ln.material_code, 'qty': ln.qty, 'material_name': ln.material_name}
                for ln in order.lines.all()
            ]
            existing.append({'material_code': mat_code, 'qty': mat_qty})
            try:
                order = set_disassembly_lines(order_id=order.pk, lines=existing)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, 'Đã thêm dòng thu hồi.')
                return redirect('san_xuat:dispatch_disassembly_detail', pk=order.pk)
    return render(request, 'san_xuat/disassembly_detail.html', {
        **_perm_ctx(request),
        'order': order,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_schedule(request):
    from datetime import datetime, timedelta

    from django.db.models import Q

    can_update = _perm_ctx(request).get('can_update')
    today = timezone.localdate()
    week_param = (request.GET.get('week') or '').strip()
    if week_param:
        try:
            week_start = datetime.strptime(week_param, '%Y-%m-%d').date()
        except ValueError:
            week_start = today - timedelta(days=today.weekday())
    else:
        week_start = today - timedelta(days=today.weekday())

    if request.method == 'POST' and can_update:
        form = ScheduleMoUpdateForm(request.POST)
        if form.is_valid():
            try:
                mo = update_mo_schedule(
                    production_order_id=form.cleaned_data['production_order_id'],
                    planned_start=form.cleaned_data.get('planned_start'),
                    planned_end=form.cleaned_data.get('planned_end'),
                    team_label=form.cleaned_data.get('team_label'),
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã cập nhật lịch {mo.code}.')
        else:
            messages.error(request, 'Không cập nhật được lịch — kiểm tra lại form.')
        return redirect(f"{request.path}?week={week_start.isoformat()}")

    week_end = week_start + timedelta(days=6)
    prev_week = (week_start - timedelta(days=7)).isoformat()
    next_week = (week_start + timedelta(days=7)).isoformat()

    mos = list(
        SxProductionOrder.objects.filter(is_demo=False)
        .filter(
            Q(planned_start__range=(week_start, week_end))
            | Q(planned_end__range=(week_start, week_end))
            | Q(planned_start__isnull=True, order_date__range=(week_start, week_end))
        )
        .order_by('planned_start', 'order_date', 'code')[:500]
    )

    def _mo_on_day(mo, day):
        if mo.planned_start and mo.planned_end:
            return mo.planned_start <= day <= mo.planned_end
        if mo.planned_start:
            return mo.planned_start == day
        return mo.order_date == day

    days = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_orders = [mo for mo in mos if _mo_on_day(mo, day)]
        days.append({'date': day, 'orders': day_orders, 'is_today': day == today})

    return render(request, 'san_xuat/dispatch_schedule.html', {
        **_perm_ctx(request),
        'week_start': week_start,
        'week_end': week_end,
        'prev_week': prev_week,
        'next_week': next_week,
        'days': days,
        'mos': mos,
        'order_count': len(mos),
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_material_issue_req(request):
    from san_xuat.services.mo_progress import pending_material_issue_qs

    queue = (request.GET.get('queue') or '').strip().lower()
    base_qs = (
        SxMaterialIssueRequest.objects.filter(is_demo=False)
        .order_by('-request_date', '-pk')
        .select_related('production_order', 'stock_issue')
    )
    pending_count = pending_material_issue_qs().count()
    if queue in ('pending', 'cho-duyet', '1'):
        base_qs = pending_material_issue_qs()
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_MATERIAL_ISSUE)
    return render(request, 'san_xuat/dispatch_material_issue_req_list.html', {
        **_perm_ctx(request),
        'page_title': 'Yêu cầu xuất vật tư',
        'requests': requests_qs,
        'pending_ycx_count': pending_count,
        'queue_pending': queue in ('pending', 'cho-duyet', '1'),
        **fctx,
    })


def _ycx_detail_context(req):
    from kho_npl.models import StockBalance, WarehouseLocation

    locations = list(WarehouseLocation.objects.filter(is_active=True).order_by('code')[:200])
    line_rows = []
    for line in req.lines.select_related('preferred_location').all():
        balances = []
        mat = None
        code = (line.material_code or '').strip()
        if code:
            from kho_npl.models import Material
            mat = Material.objects.filter(code__iexact=code, is_active=True).first()
        if mat:
            balances = list(
                StockBalance.objects.filter(material=mat, quantity__gt=0)
                .select_related('location')
                .order_by('location__code')[:12]
            )
        line_rows.append({'line': line, 'balances': balances})
    return {'locations': locations, 'line_rows': line_rows}


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_material_issue_req_detail(request, pk: int):
    req = (
        SxMaterialIssueRequest.objects.select_related('production_order', 'stock_issue')
        .prefetch_related('lines__preferred_location')
        .get(pk=pk)
    )
    can_update = _perm_ctx(request).get('can_update')
    stock_issue = req.stock_issue
    form = MaterialIssueApproveForm()

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'save_locations' and can_update and not req.stock_issue_id:
            from kho_npl.models import WarehouseLocation

            updated = 0
            for line in req.lines.all():
                raw = (request.POST.get(f'loc_{line.pk}') or '').strip()
                loc = None
                if raw.isdigit():
                    loc = WarehouseLocation.objects.filter(pk=int(raw), is_active=True).first()
                if line.preferred_location_id != (loc.pk if loc else None):
                    line.preferred_location = loc
                    line.save(update_fields=['preferred_location'])
                    updated += 1
            messages.success(
                request,
                f'Đã lưu vị trí ưu tiên ({updated} dòng cập nhật).' if updated else 'Không có thay đổi vị trí.',
            )
            return redirect('san_xuat:dispatch_material_issue_req_detail', pk=req.pk)

        if action == 'approve' and can_update and req.status in ('draft', 'submitted', 'approved'):
            form = MaterialIssueApproveForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    res = approve_material_issue(
                        request_id=req.pk,
                        user=request.user,
                        attachment=form.cleaned_data.get('attachment') or None,
                    )
                except DispatchError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Yêu cầu xuất {res.request.code} đã duyệt.')
                    return redirect('san_xuat:dispatch_material_issue_req_detail', pk=res.request.pk)
            else:
                messages.error(request, 'Không duyệt được yêu cầu xuất — kiểm tra lại form.')

    else:
        form = MaterialIssueApproveForm()

    return render(request, 'san_xuat/dispatch_material_issue_req_detail.html', {
        **_perm_ctx(request),
        'req': req,
        'form': form,
        'can_update': can_update,
        'stock_issue': stock_issue,
        **_ycx_detail_context(req),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_prod_stats(request):
    base_qs = (
        SxProductionStat.objects.filter(is_demo=False)
        .order_by('-stat_date', '-pk')
        .select_related('production_order')
    )
    stats, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PROD_STAT)
    return render(request, 'san_xuat/dispatch_prod_stats_list.html', {
        **_perm_ctx(request),
        'stats': stats,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_prod_stats_create(request):
    mo_id = request.GET.get('mo')
    mo = get_object_or_404(SxProductionOrder, pk=mo_id) if mo_id else None
    if request.method == 'POST':
        mo = get_object_or_404(SxProductionOrder, pk=request.POST.get('production_order'))
        form = ProductionStatCreateForm(request.POST)
        if form.is_valid():
            try:
                stat = create_production_stat(
                    production_order_id=mo.pk,
                    stat_date=form.cleaned_data['stat_date'],
                    process_name=form.cleaned_data.get('process_name') or '',
                    qty_good=form.cleaned_data.get('qty_good') or 0,
                    qty_defect=form.cleaned_data.get('qty_defect') or 0,
                    team_label=form.cleaned_data.get('team_label') or '',
                    notes=form.cleaned_data.get('notes') or '',
                    code=form.cleaned_data.get('code') or None,
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo TKSX {stat.code}.')
                return redirect('san_xuat:dispatch_prod_stats_detail', pk=stat.pk)
        else:
            messages.error(request, 'Không tạo được TKSX — kiểm tra lại form.')
    else:
        initial = {'stat_date': timezone.localdate()}
        if mo:
            initial['team_label'] = mo.team_label
        form = ProductionStatCreateForm(initial=initial)
    return render(request, 'san_xuat/dispatch_prod_stats_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mo': mo,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_prod_stats_detail(request, pk: int):
    stat = get_object_or_404(
        SxProductionStat.objects.select_related('production_order'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and stat.status == SxProductionStat.STATUS_DRAFT:
            from san_xuat.services.gates import check_issue_before_stat

            gate = check_issue_before_stat(mo=stat.production_order)
            if gate.should_warn:
                messages.warning(request, gate.message)
            try:
                stat = confirm_stat(stat_id=stat.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f'Thống kê {stat.code} đã xác nhận, cập nhật lệnh và tự sinh yêu cầu kiểm tra/cảnh báo (nếu có).',
                )
                return redirect('san_xuat:dispatch_prod_stats_detail', pk=stat.pk)
        elif action == 'create_yckt' and can_update:
            try:
                qc_req = create_request_from_stat(stat_id=stat.pk, auto=False)
            except QcError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo YCKT {qc_req.code} từ TKSX.')
                return redirect('san_xuat:qc_request_detail', pk=qc_req.pk)

    qc_requests = stat.qc_requests.filter(is_demo=False).order_by('-request_date', '-pk')
    qc_alerts = stat.qc_alerts.filter(is_demo=False).order_by('-created_at')
    return render(request, 'san_xuat/dispatch_prod_stats_detail.html', {
        **_perm_ctx(request),
        'stat': stat,
        'can_update': can_update,
        'qc_requests': qc_requests,
        'qc_alerts': qc_alerts,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_fg_receipt_req(request):
    base_qs = (
        SxFgReceiptRequest.objects.filter(is_demo=False)
        .select_related('production_order', 'production_stat')
        .order_by('-request_date', '-pk')
    )
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_FG_RECEIPT)
    return render(request, 'san_xuat/dispatch_fg_receipt_req_list.html', {
        **_perm_ctx(request),
        'requests': requests_qs,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_fg_receipt_req_create(request):
    mo = None
    stat = None
    if request.method == 'POST':
        form = FgReceiptCreateForm(request.POST)
        mo_id = request.POST.get('mo_id')
        stat_id = request.POST.get('stat_id')
        if mo_id and str(mo_id).isdigit():
            mo = get_object_or_404(SxProductionOrder, pk=int(mo_id))
        if stat_id and str(stat_id).isdigit():
            stat = get_object_or_404(SxProductionStat, pk=int(stat_id))
            mo = stat.production_order
        if form.is_valid() and mo:
            try:
                fg_req = create_fg_receipt_from_mo(
                    production_order_id=mo.pk,
                    stat_id=stat.pk if stat else None,
                    qty=form.cleaned_data['qty'],
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo YCNTP {fg_req.code}.')
                return redirect('san_xuat:dispatch_fg_receipt_req_detail', pk=fg_req.pk)
        elif not mo:
            messages.error(request, 'Thiếu LSX nguồn.')
        else:
            messages.error(request, 'Không tạo được YCNTP — kiểm tra lại form.')
    else:
        initial = {}
        mo_id = request.GET.get('mo')
        stat_id = request.GET.get('stat')
        if stat_id and str(stat_id).isdigit():
            stat = get_object_or_404(SxProductionStat, pk=int(stat_id))
            mo = stat.production_order
            initial['qty'] = stat.qty_good or mo.qty_done or 0
        elif mo_id and str(mo_id).isdigit():
            mo = get_object_or_404(SxProductionOrder, pk=int(mo_id))
            initial['qty'] = mo.qty_done or mo.qty
        form = FgReceiptCreateForm(initial=initial)
    return render(request, 'san_xuat/dispatch_fg_receipt_req_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mo': mo,
        'stat': stat,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_fg_receipt_req_detail(request, pk: int):
    fg_req = get_object_or_404(
        SxFgReceiptRequest.objects.select_related('production_order', 'production_stat'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    link_form = FgReceiptLinkKvForm()
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'submit' and can_update and fg_req.status == SxFgReceiptRequest.STATUS_DRAFT:
            try:
                fg_req = submit_fg_receipt(request_id=fg_req.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'YCNTP {fg_req.code} đã gửi.')
                return redirect('san_xuat:dispatch_fg_receipt_req_detail', pk=fg_req.pk)
        elif action == 'link_kv' and can_update:
            link_form = FgReceiptLinkKvForm(request.POST)
            if link_form.is_valid():
                try:
                    fg_req = link_kv_purchase(
                        request_id=fg_req.pk,
                        kv_purchase_kiotviet_id=link_form.cleaned_data.get('kv_purchase_kiotviet_id'),
                        kv_purchase_code=link_form.cleaned_data.get('kv_purchase_code') or '',
                    )
                except DispatchError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã liên kết phiếu nhập KV {fg_req.kv_purchase_code}.')
                    return redirect('san_xuat:dispatch_fg_receipt_req_detail', pk=fg_req.pk)
            messages.error(request, 'Không liên kết được phiếu nhập KV.')
    return render(request, 'san_xuat/dispatch_fg_receipt_req_detail.html', {
        **_perm_ctx(request),
        'fg_req': fg_req,
        'can_update': can_update,
        'link_form': link_form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_npl_surplus(request):
    base_qs = (
        SxNplSurplus.objects.filter(is_demo=False)
        .select_related('production_order', 'disassembly_order', 'stock_adjustment')
        .order_by('-recorded_at', '-pk')
    )
    items, fctx = prepare_hub_list(request, base_qs, SX_FILTER_NPL_SURPLUS)
    return render(request, 'san_xuat/npl_surplus_list.html', {
        **_perm_ctx(request),
        'items': items,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_npl_surplus_create(request):
    if request.method == 'POST':
        form = NplSurplusCreateForm(request.POST)
        if form.is_valid():
            mo = form.cleaned_data.get('production_order')
            try:
                item = create_npl_surplus(
                    material_code=form.cleaned_data['material_code'],
                    material_name=form.cleaned_data.get('material_name') or '',
                    qty=form.cleaned_data['qty'],
                    recorded_at=form.cleaned_data.get('recorded_at'),
                    production_order_id=mo.pk if mo else None,
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo NPL thừa {item.code}.')
                return redirect('san_xuat:dispatch_npl_surplus_detail', pk=item.pk)
        messages.error(request, 'Không tạo được NPL thừa — kiểm tra lại form.')
    else:
        form = NplSurplusCreateForm(initial={'recorded_at': timezone.localdate()})
    return render(request, 'san_xuat/npl_surplus_form.html', {
        **_perm_ctx(request),
        'form': form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_npl_surplus_detail(request, pk: int):
    item = get_object_or_404(
        SxNplSurplus.objects.select_related(
            'production_order', 'disassembly_order', 'stock_adjustment',
        ),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and item.status == SxNplSurplus.STATUS_DRAFT:
            try:
                item = confirm_npl_surplus(surplus_id=item.pk, user=request.user)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f'Đã nhập kho NPL thừa {item.code}'
                    + (f' — ĐC {item.stock_adjustment.number}' if item.stock_adjustment_id else ''),
                )
                return redirect('san_xuat:dispatch_npl_surplus_detail', pk=item.pk)
    return render(request, 'san_xuat/npl_surplus_detail.html', {
        **_perm_ctx(request),
        'item': item,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_handover(request):
    base_qs = (
        SxWipHandover.objects.filter(is_demo=False)
        .select_related('production_order')
        .order_by('-handover_date', '-pk')
    )
    handovers, fctx = prepare_hub_list(request, base_qs, SX_FILTER_WIP_HANDOVER)
    return render(request, 'san_xuat/wip_handover_list.html', {
        **_perm_ctx(request),
        'handovers': handovers,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_wip_handover_create(request):
    mo = None
    process_steps: list[str] = []
    if request.method == 'POST':
        form = WipHandoverCreateForm(request.POST)
        if form.is_valid():
            try:
                handover = create_wip_handover(
                    production_order_id=form.cleaned_data['production_order'].pk,
                    from_process=form.cleaned_data['from_process'],
                    to_process=form.cleaned_data['to_process'],
                    qty=form.cleaned_data['qty'],
                    handover_date=form.cleaned_data.get('handover_date'),
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo bàn giao {handover.code}.')
                return redirect('san_xuat:dispatch_wip_handover_detail', pk=handover.pk)
        messages.error(request, 'Không tạo được bàn giao — kiểm tra lại form.')
    else:
        initial = {'handover_date': timezone.localdate()}
        mo_id = request.GET.get('mo')
        if mo_id and str(mo_id).isdigit():
            mo = get_object_or_404(SxProductionOrder, pk=int(mo_id))
            initial['production_order'] = mo.pk
            if mo.bom_version_id:
                process_steps = list(
                    mo.bom_version.process_steps.order_by('sequence').values_list('process_name', flat=True)
                )
                if len(process_steps) >= 2:
                    initial['from_process'] = process_steps[0]
                    initial['to_process'] = process_steps[1]
                elif len(process_steps) == 1:
                    initial['from_process'] = process_steps[0]
        form = WipHandoverCreateForm(initial=initial)
    return render(request, 'san_xuat/wip_handover_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mo': mo,
        'process_steps': process_steps,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_handover_detail(request, pk: int):
    handover = get_object_or_404(
        SxWipHandover.objects.select_related('production_order'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and handover.status == SxWipHandover.STATUS_PENDING:
            try:
                handover = confirm_wip_handover(handover_id=handover.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Bàn giao {handover.code} đã xác nhận.')
                return redirect('san_xuat:dispatch_wip_handover_detail', pk=handover.pk)
        elif action == 'reject' and can_update and handover.status == SxWipHandover.STATUS_PENDING:
            try:
                handover = reject_wip_handover(
                    handover_id=handover.pk,
                    notes=(request.POST.get('reject_notes') or '').strip(),
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Bàn giao {handover.code} đã từ chối.')
                return redirect('san_xuat:dispatch_wip_handover_detail', pk=handover.pk)
    return render(request, 'san_xuat/wip_handover_detail.html', {
        **_perm_ctx(request),
        'handover': handover,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_return(request):
    base_qs = (
        SxWipReturn.objects.filter(is_demo=False)
        .select_related('production_order', 'handover')
        .order_by('-return_date', '-pk')
    )
    returns, fctx = prepare_hub_list(request, base_qs, SX_FILTER_WIP_RETURN)
    return render(request, 'san_xuat/wip_return_list.html', {
        **_perm_ctx(request),
        'returns': returns,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_wip_return_create(request):
    if request.method == 'POST':
        form = WipReturnCreateForm(request.POST)
        if form.is_valid():
            ho = form.cleaned_data.get('handover')
            try:
                item = create_wip_return(
                    production_order_id=form.cleaned_data['production_order'].pk,
                    qty=form.cleaned_data['qty'],
                    reason=form.cleaned_data.get('reason') or '',
                    handover_id=ho.pk if ho else None,
                    from_process=form.cleaned_data.get('from_process') or '',
                    to_process=form.cleaned_data.get('to_process') or '',
                    return_date=form.cleaned_data.get('return_date'),
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo phiếu trả {item.code}.')
                return redirect('san_xuat:dispatch_wip_return_detail', pk=item.pk)
        messages.error(request, 'Không tạo được phiếu trả — kiểm tra lại form.')
    else:
        form = WipReturnCreateForm(initial={'return_date': timezone.localdate()})
    return render(request, 'san_xuat/wip_return_form.html', {
        **_perm_ctx(request),
        'form': form,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_return_detail(request, pk: int):
    item = get_object_or_404(
        SxWipReturn.objects.select_related('production_order', 'handover'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and item.status == SxWipReturn.STATUS_DRAFT:
            try:
                item = confirm_wip_return(return_id=item.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã xác nhận {item.code}.')
                return redirect('san_xuat:dispatch_wip_return_detail', pk=item.pk)
        elif action == 'cancel' and item.status == SxWipReturn.STATUS_DRAFT:
            try:
                item = cancel_wip_return(return_id=item.pk)
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã hủy {item.code}.')
                return redirect('san_xuat:dispatch_wip_return_detail', pk=item.pk)
    return render(request, 'san_xuat/wip_return_detail.html', {
        **_perm_ctx(request),
        'item': item,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_handover_status(request):
    qs = SxWipHandover.objects.filter(is_demo=False).select_related('production_order')
    pending = qs.filter(status=SxWipHandover.STATUS_PENDING).count()
    done = qs.filter(status=SxWipHandover.STATUS_DONE).count()
    rejected = qs.filter(status=SxWipHandover.STATUS_REJECTED).count()
    recent = qs.order_by('-handover_date', '-pk')[:50]
    return render(request, 'san_xuat/wip_handover_status.html', {
        **_perm_ctx(request),
        'pending': pending,
        'done': done,
        'rejected': rejected,
        'recent': recent,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_stub(request):
    qc_qs = lambda model: model.objects.filter(is_demo=False)
    open_requests = qc_qs(SxQcRequest).filter(status='open').count()
    pending_inspections = qc_qs(SxQcInspection).filter(result=SxQcInspection.RESULT_PENDING).count()
    open_alerts = qc_qs(SxQcAlert).filter(status=SxQcAlert.STATUS_OPEN).count()
    fail_recent = qc_qs(SxQcInspection).filter(result=SxQcInspection.RESULT_FAIL).count()
    pass_recent = qc_qs(SxQcInspection).filter(result=SxQcInspection.RESULT_PASS).count()
    catalog_counts = {
        'criteria': qc_qs(SxQcCriteria).filter(is_active=True).count(),
        'standard_sets': qc_qs(SxQcStandardSet).filter(is_active=True).count(),
        'defects': qc_qs(SxQcDefect).filter(is_active=True).count(),
    }
    return render(request, 'san_xuat/hub_qc.html', {
        **_perm_ctx(request),
        'open_requests': open_requests,
        'pending_inspections': pending_inspections,
        'open_alerts': open_alerts,
        'fail_recent': fail_recent,
        'pass_recent': pass_recent,
        'catalog_counts': catalog_counts,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_request(request):
    base_qs = (
        SxQcRequest.objects.filter(is_demo=False)
        .select_related('production_order')
        .order_by('-request_date', '-pk')
    )
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_QC_REQUEST)
    return render(request, 'san_xuat/qc_request_list.html', {
        **_perm_ctx(request),
        'requests': requests_qs,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_request_create(request):
    mo = None
    stat = None
    if request.method == 'POST':
        form = QcRequestForm(request.POST)
        if form.is_valid():
            qc_req = form.save(commit=False)
            if not qc_req.code:
                qc_req.code = _next_code('YCKT', SxQcRequest)
            qc_req.is_demo = False
            qc_req.save()
            messages.success(request, f'Đã tạo YCKT {qc_req.code}.')
            return redirect('san_xuat:qc_request_detail', pk=qc_req.pk)
        messages.error(request, 'Không tạo được YCKT - kiểm tra lại form.')
    else:
        initial = {}
        mo_id = request.GET.get('mo')
        stat_id = request.GET.get('stat')
        if mo_id and str(mo_id).isdigit():
            mo = get_object_or_404(SxProductionOrder, pk=int(mo_id))
            initial.update({
                'production_order': mo.pk,
                'product_code': mo.product_code,
                'product_name': mo.product_name,
                'stage_name': mo.team_label,
                'qty': mo.qty,
            })
        if stat_id and str(stat_id).isdigit():
            stat = get_object_or_404(SxProductionStat, pk=int(stat_id))
            mo = stat.production_order
            initial.update({
                'production_order': mo.pk,
                'product_code': mo.product_code,
                'product_name': mo.product_name,
                'stage_name': stat.process_name,
                'qty': stat.qty_good or stat.qty_defect or 0,
            })
        form = QcRequestForm(initial=initial)
    return render(request, 'san_xuat/qc_request_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mo': mo,
        'stat': stat,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_request_detail(request, pk: int):
    qc_req = get_object_or_404(
        SxQcRequest.objects.select_related('production_order', 'production_stat').prefetch_related('inspections'),
        pk=pk,
    )
    return render(request, 'san_xuat/qc_request_detail.html', {
        **_perm_ctx(request),
        'qc_req': qc_req,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sheet(request):
    base_qs = (
        SxQcInspection.objects.filter(is_demo=False)
        .select_related('qc_request', 'standard_set')
        .order_by('-inspected_at', '-pk')
    )
    inspections, fctx = prepare_hub_list(request, base_qs, SX_FILTER_QC_SHEET)
    return render(request, 'san_xuat/qc_sheet_list.html', {
        **_perm_ctx(request),
        'inspections': inspections,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_sheet_create(request):
    qc_req = None
    if request.method == 'POST':
        form = QcInspectionCreateForm(request.POST)
        if form.is_valid():
            try:
                inspection = create_inspection_from_request(
                    request_id=form.cleaned_data['qc_request'].pk,
                    standard_id=form.cleaned_data['standard_set'].pk if form.cleaned_data.get('standard_set') else None,
                    code=form.cleaned_data.get('code') or None,
                    inspected_at=form.cleaned_data.get('inspected_at'),
                    notes=form.cleaned_data.get('notes') or '',
                )
            except QcError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo PKT {inspection.code}.')
                return redirect('san_xuat:qc_sheet_detail', pk=inspection.pk)
        messages.error(request, 'Không tạo được PKT - kiểm tra lại form.')
    else:
        initial = {}
        req_id = request.GET.get('request')
        if req_id and str(req_id).isdigit():
            qc_req = get_object_or_404(SxQcRequest, pk=int(req_id))
            initial['qc_request'] = qc_req.pk
        form = QcInspectionCreateForm(initial=initial)
    return render(request, 'san_xuat/qc_sheet_form.html', {
        **_perm_ctx(request),
        'form': form,
        'qc_req': qc_req,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sheet_detail(request, pk: int):
    inspection = get_object_or_404(
        SxQcInspection.objects.select_related('qc_request', 'standard_set').prefetch_related(
            'criteria_lines__criteria',
            'defect_lines__defect',
        ),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if inspection.status != 'done':
        seed_inspection_criteria_lines(inspection=inspection)
        inspection = (
            SxQcInspection.objects.select_related('qc_request', 'standard_set')
            .prefetch_related('criteria_lines__criteria', 'defect_lines__defect')
            .get(pk=pk)
        )

    criteria_forms = []
    if inspection.status != 'done':
        for line in inspection.criteria_lines.all():
            criteria_forms.append({
                'line': line,
                'form': QcInspectionCriteriaLineForm(
                    prefix=f'crit_{line.pk}',
                    instance=line,
                    data=request.POST if request.method == 'POST' else None,
                ),
            })

    defect_initial = [
        {'defect': line.defect_id, 'qty': line.qty, 'notes': line.notes}
        for line in inspection.defect_lines.all()
    ]
    defect_formset = QcInspectionDefectLineFormSet(
        prefix='defects',
        initial=defect_initial,
        data=request.POST if request.method == 'POST' else None,
    )

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        finalize_form = QcInspectionFinalizeForm(request.POST, instance=inspection)
        if action == 'finalize' and can_update and inspection.status != 'done':
            criteria_valid = all(item['form'].is_valid() for item in criteria_forms)
            if finalize_form.is_valid() and criteria_valid and defect_formset.is_valid():
                try:
                    crit_inputs = [
                        CriteriaLineInput(
                            line_id=item['line'].pk,
                            is_pass=item['form'].cleaned_data.get('is_pass'),
                            value_text=item['form'].cleaned_data.get('value_text') or '',
                            value_number=item['form'].cleaned_data.get('value_number'),
                            notes=item['form'].cleaned_data.get('notes') or '',
                        )
                        for item in criteria_forms
                    ]
                    defect_inputs = []
                    for form in defect_formset:
                        defect = form.cleaned_data.get('defect')
                        qty = form.cleaned_data.get('qty') or Decimal('0')
                        if defect and qty > 0:
                            defect_inputs.append(
                                DefectLineInput(
                                    defect_id=defect.pk,
                                    qty=qty,
                                    notes=form.cleaned_data.get('notes') or '',
                                )
                            )
                    inspection = finalize_inspection(
                        inspection_id=inspection.pk,
                        qty_pass=finalize_form.cleaned_data.get('qty_pass'),
                        qty_fail=finalize_form.cleaned_data.get('qty_fail'),
                        notes=finalize_form.cleaned_data.get('notes') or '',
                        criteria_lines=crit_inputs,
                        defect_lines=defect_inputs,
                    )
                except QcError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'PKT {inspection.code} đã chốt kết quả.')
                    return redirect('san_xuat:qc_sheet_detail', pk=inspection.pk)
            messages.error(request, 'Không chốt được PKT - kiểm tra lại dữ liệu.')
    else:
        finalize_form = QcInspectionFinalizeForm(instance=inspection)

    return render(request, 'san_xuat/qc_sheet_detail.html', {
        **_perm_ctx(request),
        'inspection': inspection,
        'form': finalize_form,
        'criteria_forms': criteria_forms,
        'defect_formset': defect_formset,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_alerts(request):
    base_qs = (
        SxQcAlert.objects.filter(is_demo=False)
        .select_related('production_order', 'production_stat', 'qc_inspection')
        .order_by('-created_at', '-pk')
    )
    status = (request.GET.get('status') or '').strip()
    if status:
        base_qs = base_qs.filter(status=status)
    preserve = {'status': status} if status else None
    alerts, fctx = prepare_hub_list(request, base_qs, SX_FILTER_QC_ALERT, preserve=preserve)
    return render(request, 'san_xuat/qc_alerts_list.html', {
        **_perm_ctx(request),
        'alerts': alerts,
        'status_filter': status,
        'open_count': SxQcAlert.objects.filter(is_demo=False, status=SxQcAlert.STATUS_OPEN).count(),
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_alert_detail(request, pk: int):
    alert = get_object_or_404(
        SxQcAlert.objects.select_related(
            'production_order', 'production_stat', 'qc_request', 'qc_inspection',
        ),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'ack' and can_update and alert.status == SxQcAlert.STATUS_OPEN:
            try:
                alert = acknowledge_alert(alert_id=alert.pk)
            except QcError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Cảnh báo {alert.code} đã được ghi nhận xử lý.')
                return redirect('san_xuat:qc_alert_detail', pk=alert.pk)
    return render(request, 'san_xuat/qc_alert_detail.html', {
        **_perm_ctx(request),
        'alert': alert,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_criteria(request):
    return _qc_catalog_list(
        request,
        title='Tiêu chí chất lượng',
        subtitle='Danh mục tiêu chí QC',
        model=SxQcCriteria,
        fields=['code', 'name', 'group', 'kind'],
        labels=['Mã', 'Tên', 'Nhóm', 'Loại'],
        create_url_name='san_xuat:qc_criteria_create',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_criteria_group(request):
    return _qc_catalog_list(
        request,
        title='Nhóm tiêu chí chất lượng',
        subtitle='Nhóm tiêu chí QC',
        model=SxQcCriteriaGroup,
        fields=['code', 'name', 'is_active'],
        labels=['Mã', 'Tên', 'Active'],
        create_url_name='san_xuat:qc_criteria_group_create',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sampling(request):
    return _qc_catalog_list(
        request,
        title='Phương pháp chọn mẫu',
        subtitle='Quy tắc lấy mẫu QC',
        model=SxQcSamplingMethod,
        fields=['code', 'name', 'method_type', 'sample_value'],
        labels=['Mã', 'Tên', 'Loại', 'Giá trị'],
        create_url_name='san_xuat:qc_sampling_create',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_standard_set(request):
    return _qc_catalog_list(
        request,
        title='Bộ tiêu chuẩn kiểm tra chất lượng',
        subtitle='Bộ tiêu chuẩn áp dụng theo sản phẩm',
        model=SxQcStandardSet,
        fields=['code', 'name', 'product_code', 'stage_name', 'defect_tolerance_pct', 'sampling_method'],
        labels=['Mã', 'Tên', 'Mã SP', 'Công đoạn', 'Ngưỡng %', 'Chọn mẫu'],
        create_url_name='san_xuat:qc_standard_set_create',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_defect(request):
    return _qc_catalog_list(
        request,
        title='Lỗi kiểm tra chất lượng',
        subtitle='Danh mục mã lỗi QC',
        model=SxQcDefect,
        fields=['code', 'name', 'group', 'severity'],
        labels=['Mã', 'Tên', 'Nhóm', 'Mức độ'],
        create_url_name='san_xuat:qc_defect_create',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_defect_group(request):
    return _qc_catalog_list(
        request,
        title='Nhóm lỗi kiểm tra chất lượng',
        subtitle='Nhóm lỗi QC',
        model=SxQcDefectGroup,
        fields=['code', 'name', 'is_active'],
        labels=['Mã', 'Tên', 'Active'],
        create_url_name='san_xuat:qc_defect_group_create',
    )


def _qc_catalog_list(request, *, title, subtitle, model, fields, labels, create_url_name):
    qs = model.objects.filter(is_demo=False).order_by('code')[:200]
    return render(request, 'san_xuat/qc_catalog_list.html', {
        **_perm_ctx(request),
        'hub_title': title,
        'hub_subtitle': subtitle,
        'columns': labels,
        'rows': _rows_from_queryset(qs, fields),
        'create_url_name': create_url_name,
    })


def _qc_catalog_create(request, *, form_class, title, success_label):
    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.is_demo = False
            obj.save()
            messages.success(request, f'Đã tạo {success_label}.')
            return redirect(request.path)
        messages.error(request, f'Không tạo được {success_label}.')
    else:
        form = form_class()
    return render(request, 'san_xuat/qc_catalog_form.html', {
        **_perm_ctx(request),
        'form': form,
        'page_title': title,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_criteria_create(request):
    return _qc_catalog_create(request, form_class=QcCriteriaForm, title='Thêm tiêu chí chất lượng', success_label='tiêu chí QC')


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_criteria_group_create(request):
    return _qc_catalog_create(request, form_class=QcCriteriaGroupForm, title='Thêm nhóm tiêu chí chất lượng', success_label='nhóm tiêu chí QC')


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_sampling_create(request):
    return _qc_catalog_create(request, form_class=QcSamplingMethodForm, title='Thêm phương pháp chọn mẫu', success_label='phương pháp chọn mẫu')


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_standard_set_create(request):
    return _qc_catalog_create(request, form_class=QcStandardSetForm, title='Thêm bộ tiêu chuẩn chất lượng', success_label='bộ tiêu chuẩn QC')


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_defect_create(request):
    return _qc_catalog_create(request, form_class=QcDefectForm, title='Thêm lỗi chất lượng', success_label='lỗi QC')


@module_perm_required(MODULE_SAN_XUAT, 'create')
def qc_defect_group_create(request):
    return _qc_catalog_create(request, form_class=QcDefectGroupForm, title='Thêm nhóm lỗi chất lượng', success_label='nhóm lỗi QC')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def process_stub(request):
    return redirect(f"{reverse('san_xuat:doc_list')}?tab=process")


# --- Giai đoạn 3 ---


@module_perm_required(MODULE_SAN_XUAT, 'view')
def work_assignment_list(request):
    from san_xuat.services.phase3 import Phase3Error, complete_work_assignment

    qs = (
        SxWorkAssignment.objects.filter(is_demo=False)
        .select_related('production_order', 'work_center', 'work_task', 'assignee')
        .order_by('-created_at', '-pk')
    )
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)
    items, fctx = prepare_hub_list(request, qs, SX_FILTER_WORK_ASSIGN)
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        pk = request.POST.get('pk')
        if action == 'complete' and pk and str(pk).isdigit():
            try:
                item = complete_work_assignment(assignment_id=int(pk))
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã hoàn thành {item.code}.')
            return redirect('san_xuat:work_assignment_list')
    return render(request, 'san_xuat/work_assignment_list.html', {
        **_perm_ctx(request),
        'items': items,
        'status_filter': status_filter,
        'list_filter_status_options': [
            ('', 'Tất cả TT'),
            ('open', 'Đang giao'),
            ('done', 'Hoàn thành'),
            ('cancelled', 'Hủy'),
        ],
        'list_filter_status_value': status_filter,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def work_assignment_create(request):
    from san_xuat.services.phase3 import Phase3Error, create_work_assignment

    if request.method == 'POST':
        form = WorkAssignmentCreateForm(request.POST, assigner=request.user)
        if form.is_valid():
            center = form.cleaned_data.get('work_center')
            assignee = form.cleaned_data.get('assignee')
            create_task = bool(form.cleaned_data.get('create_portal_task'))
            try:
                item = create_work_assignment(
                    production_order_id=form.cleaned_data['production_order'].pk,
                    title=form.cleaned_data['title'],
                    process_name=form.cleaned_data.get('process_name') or '',
                    assignee_label=form.cleaned_data.get('assignee_label') or '',
                    due_date=form.cleaned_data.get('due_date'),
                    notes=form.cleaned_data.get('notes') or '',
                    work_center_id=center.pk if center else None,
                    assignee_id=assignee.pk if assignee else None,
                    create_portal_task=create_task,
                    assigner=request.user if create_task else None,
                )
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                msg = f'Đã tạo giao việc {item.code}.'
                if item.work_task_id:
                    msg += f' Đã tạo WorkTask #{item.work_task_id}.'
                messages.success(request, msg)
                return redirect('san_xuat:work_assignment_list')
        messages.error(request, 'Không tạo được giao việc.')
    else:
        initial = {'create_portal_task': True}
        mo_id = request.GET.get('mo')
        if mo_id and str(mo_id).isdigit():
            initial['production_order'] = int(mo_id)
        form = WorkAssignmentCreateForm(initial=initial, assigner=request.user)
    return render(request, 'san_xuat/phase3_form.html', {
        **_perm_ctx(request),
        'form': form,
        'title': 'Giao việc theo LSX',
        'back_url': 'san_xuat:work_assignment_list',
        'hint': 'Tick «Tạo công việc module Công việc» để đẩy sang tasks (cần chọn người nhận portal).',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def traceability(request):
    from san_xuat.services.gates import get_trace_min_timeline_events
    from san_xuat.services.mo_progress import analyze_trace_gaps
    from san_xuat.services.phase3 import trace_production

    result = None
    gaps = []
    show_gaps = (request.GET.get('gaps') or '').strip() in ('1', 'true', 'yes', 'on')
    form = TraceLookupForm(request.GET or None)
    if request.GET.get('query'):
        if form.is_valid():
            result = trace_production(query=form.cleaned_data['query'])
            if result and result.mo and show_gaps:
                gaps = analyze_trace_gaps(
                    mo=result.mo,
                    timeline_len=len(result.timeline or []),
                    min_events=get_trace_min_timeline_events(),
                )
    return render(request, 'san_xuat/traceability.html', {
        **_perm_ctx(request),
        'form': form,
        'result': result,
        'show_gaps': show_gaps,
        'gaps': gaps,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def general_settings(request):
    """Thiết lập chung sản xuất — cổng quy trình, ngưỡng truy xuất."""
    from san_xuat.forms_settings import SxGeneralSettingsForm
    from san_xuat.hub_models import SxGeneralSettings

    cfg = SxGeneralSettings.load()
    can_update = _perm_ctx(request).get('can_update')

    if request.method == 'POST':
        if not can_update:
            messages.error(request, 'Bạn không có quyền cập nhật thiết lập.')
            return redirect('san_xuat:general_settings')
        form = SxGeneralSettingsForm(request.POST, instance=cfg)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user if request.user.is_authenticated else None
            obj.save()
            messages.success(request, 'Đã lưu thiết lập chung sản xuất.')
            return redirect('san_xuat:general_settings')
        messages.error(request, 'Không lưu được — kiểm tra lại form.')
    else:
        form = SxGeneralSettingsForm(instance=cfg)

    return render(request, 'san_xuat/general_settings.html', {
        **_perm_ctx(request),
        'form': form,
        'cfg': cfg,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def capacity_list(request):
    from san_xuat.services.overview import parse_overview_period
    from san_xuat.services.phase3 import build_capacity_load

    filters = parse_sx_list_filters(request)
    month = (request.GET.get('month') or '').strip()
    raw_from = (request.GET.get('date_from') or '').strip()
    raw_to = (request.GET.get('date_to') or '').strip()

    if month and not raw_from and not raw_to:
        date_from, date_to = parse_overview_period(month=month)
        filters = SxListFilters(
            code=filters.code,
            name=filters.name,
            date_from=date_from,
            date_to=date_to,
            dates_defaulted=False,
        )
    else:
        date_from, date_to = filters.date_from, filters.date_to
        if not date_from or not date_to:
            date_from, date_to = default_list_date_range()

    base_centers = (
        SxWorkCenter.objects.filter(is_demo=False)
        .select_related('created_by')
        .order_by('code')
    )
    centers = apply_sx_list_filters(base_centers, filters, SX_FILTER_WORK_CENTER)
    load_rows = build_capacity_load(date_from=date_from, date_to=date_to)
    preserve = {'month': month} if month else None
    from san_xuat.services.sx_settings import sx_int

    return render(request, 'san_xuat/capacity_list.html', {
        **_perm_ctx(request),
        'centers': centers,
        'load_rows': load_rows,
        'date_from': date_from,
        'date_to': date_to,
        'month_value': f'{date_from.year:04d}-{date_from.month:02d}',
        'capacity_load_warn_pct': sx_int('capacity_load_warn_pct', 80, min_v=1, max_v=200),
        'capacity_load_danger_pct': sx_int('capacity_load_danger_pct', 100, min_v=1, max_v=200),
        **sx_filter_context(filters, preserve=preserve),
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def capacity_create(request):
    from san_xuat.services.phase3 import Phase3Error, upsert_work_center

    if request.method == 'POST':
        form = WorkCenterForm(request.POST)
        if form.is_valid():
            try:
                center = upsert_work_center(
                    code=form.cleaned_data['code'],
                    name=form.cleaned_data['name'],
                    capacity_per_day=form.cleaned_data['capacity_per_day'],
                    uom_label=form.cleaned_data.get('uom_label') or 'SP',
                    team_label=form.cleaned_data.get('team_label') or '',
                    is_active=bool(form.cleaned_data.get('is_active')),
                    notes=form.cleaned_data.get('notes') or '',
                )
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã thêm {center.code}.')
                return redirect('san_xuat:capacity_list')
        messages.error(request, 'Không lưu được tổ/chuyền.')
    else:
        form = WorkCenterForm(initial={'is_active': True, 'uom_label': 'SP'})
    return render(request, 'san_xuat/phase3_form.html', {
        **_perm_ctx(request),
        'form': form,
        'title': 'Thêm năng lực SX',
        'back_url': 'san_xuat:capacity_list',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ops_report(request):
    from san_xuat.services.overview import parse_overview_period
    from san_xuat.services.phase3 import build_ops_report, export_ops_report_csv

    date_from, date_to = parse_overview_period(
        month=(request.GET.get('month') or '').strip(),
        date_from=(request.GET.get('date_from') or '').strip(),
        date_to=(request.GET.get('date_to') or '').strip(),
    )
    product_code = (request.GET.get('product_code') or '').strip()
    process_name = (request.GET.get('process_name') or '').strip()
    team_label = (request.GET.get('team_label') or '').strip()
    active_tab = (request.GET.get('tab') or 'danh-sach').strip().lower()
    allowed_tabs = {
        'danh-sach', 'theo-ngay', 'theo-sp', 'theo-to',
        'lenh-sx', 'dong-goi', 'dung-chuyen', 'kho',
    }
    if active_tab not in allowed_tabs:
        active_tab = 'danh-sach'
    report = build_ops_report(
        date_from=date_from,
        date_to=date_to,
        product_code=product_code,
        process_name=process_name,
        team_label=team_label,
    )
    if (request.GET.get('export') or '').strip() == 'csv':
        return export_ops_report_csv(report=report)

    has_filters = bool(
        product_code or process_name or team_label
        or request.GET.get('month') or request.GET.get('date_from') or request.GET.get('date_to')
    )
    return render(request, 'san_xuat/ops_report.html', {
        **_perm_ctx(request),
        'report': report,
        'month_value': f'{date_from.year:04d}-{date_from.month:02d}',
        'product_code': product_code,
        'process_name': process_name,
        'team_label': team_label,
        'active_tab': active_tab,
        'has_filters': has_filters,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def packing_list(request):
    base_qs = (
        SxPackingRecord.objects.filter(is_demo=False)
        .select_related('production_order', 'fg_receipt')
        .order_by('-pack_date', '-pk')
    )
    items, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PACKING)
    return render(request, 'san_xuat/packing_list.html', {
        **_perm_ctx(request),
        'items': items,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def packing_create(request):
    from san_xuat.services.phase3 import Phase3Error, create_packing_record

    if request.method == 'POST':
        form = PackingCreateForm(request.POST)
        line_formset = PackingLineFormSet(request.POST, prefix='lines')
        if form.is_valid() and line_formset.is_valid():
            lines = []
            for lf in line_formset:
                cd = lf.cleaned_data
                if not cd:
                    continue
                qty = cd.get('qty')
                if qty and qty > 0:
                    lines.append(cd)
            fg = form.cleaned_data.get('fg_receipt')
            try:
                item = create_packing_record(
                    production_order_id=form.cleaned_data['production_order'].pk,
                    qty=form.cleaned_data.get('qty') or None,
                    pack_date=form.cleaned_data.get('pack_date'),
                    carton_count=form.cleaned_data.get('carton_count') or 0,
                    lot_code=form.cleaned_data.get('lot_code') or '',
                    fg_receipt_id=fg.pk if fg else None,
                    notes=form.cleaned_data.get('notes') or '',
                    lines=lines,
                )
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo {item.code}.')
                return redirect('san_xuat:packing_detail', pk=item.pk)
        messages.error(request, 'Không tạo được phiếu đóng gói.')
    else:
        form = PackingCreateForm(initial={'pack_date': timezone.localdate()})
        line_formset = PackingLineFormSet(prefix='lines')
    return render(request, 'san_xuat/packing_create.html', {
        **_perm_ctx(request),
        'form': form,
        'line_formset': line_formset,
        'title': 'Ghi nhận đóng gói',
        'back_url': 'san_xuat:packing_list',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def packing_detail(request, pk: int):
    from san_xuat.services.phase3 import Phase3Error, confirm_packing_record

    item = get_object_or_404(
        SxPackingRecord.objects.select_related('production_order', 'fg_receipt').prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST' and can_update:
        if (request.POST.get('action') or '') == 'confirm' and item.status == SxPackingRecord.STATUS_DRAFT:
            try:
                item = confirm_packing_record(packing_id=item.pk)
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã xác nhận {item.code}.')
                return redirect('san_xuat:packing_detail', pk=item.pk)
    return render(request, 'san_xuat/packing_detail.html', {
        **_perm_ctx(request),
        'item': item,
        'can_update': can_update,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def subcontract_list(request):
    base_qs = (
        SxSubcontractOrder.objects.filter(is_demo=False)
        .select_related('production_order')
        .order_by('-order_date', '-pk')
    )
    items, fctx = prepare_hub_list(request, base_qs, SX_FILTER_SUBCONTRACT)
    return render(request, 'san_xuat/subcontract_list.html', {
        **_perm_ctx(request),
        'items': items,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def subcontract_create(request):
    from san_xuat.services.phase3 import Phase3Error, create_subcontract_order

    if request.method == 'POST':
        form = SubcontractCreateForm(request.POST)
        out_formset = SubcontractOutLineFormSet(request.POST, prefix='out')
        if form.is_valid() and out_formset.is_valid():
            mo = form.cleaned_data.get('production_order')
            out_lines = []
            for lf in out_formset:
                cd = lf.cleaned_data
                if not cd:
                    continue
                if cd.get('material_code') and cd.get('qty') and cd['qty'] > 0:
                    out_lines.append(cd)
            try:
                item = create_subcontract_order(
                    vendor_name=form.cleaned_data['vendor_name'],
                    product_code=form.cleaned_data['product_code'],
                    product_name=form.cleaned_data.get('product_name') or '',
                    process_name=form.cleaned_data.get('process_name') or '',
                    qty=form.cleaned_data['qty'],
                    order_date=form.cleaned_data.get('order_date'),
                    due_date=form.cleaned_data.get('due_date'),
                    production_order_id=mo.pk if mo else None,
                    notes=form.cleaned_data.get('notes') or '',
                    out_lines=out_lines,
                )
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo {item.code}.')
                return redirect('san_xuat:subcontract_detail', pk=item.pk)
        messages.error(request, 'Không tạo được lệnh GC.')
    else:
        form = SubcontractCreateForm(initial={'order_date': timezone.localdate()})
        out_formset = SubcontractOutLineFormSet(prefix='out')
    return render(request, 'san_xuat/subcontract_create.html', {
        **_perm_ctx(request),
        'form': form,
        'out_formset': out_formset,
        'title': 'Thuê gia công',
        'back_url': 'san_xuat:subcontract_list',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def subcontract_detail(request, pk: int):
    from san_xuat.hub_models import SxSubcontractMaterialLine, SxSubcontractOrder as Sub
    from san_xuat.services.phase3 import (
        Phase3Error,
        add_subcontract_material_line,
        advance_subcontract_order,
    )

    item = get_object_or_404(
        SxSubcontractOrder.objects.select_related('production_order').prefetch_related('material_lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    receive_form = SubcontractReceiveForm(initial={'qty_received': item.qty or Decimal('0')})
    add_out_form = SubcontractMaterialLineForm()

    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        if action == 'add_out':
            add_out_form = SubcontractMaterialLineForm(request.POST)
            if add_out_form.is_valid():
                cd = add_out_form.cleaned_data
                try:
                    add_subcontract_material_line(
                        order_id=item.pk,
                        direction=SxSubcontractMaterialLine.DIRECTION_OUT,
                        material_code=cd.get('material_code') or '',
                        qty=cd.get('qty') or Decimal('0'),
                        material_name=cd.get('material_name') or '',
                        uom_label=cd.get('uom_label') or 'SP',
                        lot_code=cd.get('lot_code') or '',
                    )
                except Phase3Error as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, 'Đã thêm dòng xuất đi GC.')
                    return redirect('san_xuat:subcontract_detail', pk=item.pk)
        elif action == 'receive':
            receive_form = SubcontractReceiveForm(request.POST)
            if receive_form.is_valid():
                cd = receive_form.cleaned_data
                try:
                    if cd.get('material_code'):
                        add_subcontract_material_line(
                            order_id=item.pk,
                            direction=SxSubcontractMaterialLine.DIRECTION_IN,
                            material_code=cd['material_code'],
                            qty=cd['qty_received'],
                            material_name=cd.get('material_name') or '',
                            lot_code=cd.get('lot_code') or '',
                        )
                    item = advance_subcontract_order(
                        order_id=item.pk,
                        to_status=Sub.STATUS_RECEIVED,
                        qty_received=cd['qty_received'],
                    )
                except Phase3Error as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'{item.code} → {item.get_status_display()}.')
                    return redirect('san_xuat:subcontract_detail', pk=item.pk)
        else:
            to_status = (request.POST.get('to_status') or '').strip()
            if to_status:
                try:
                    item = advance_subcontract_order(order_id=item.pk, to_status=to_status)
                except Phase3Error as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'{item.code} → {item.get_status_display()}.')
                    return redirect('san_xuat:subcontract_detail', pk=item.pk)

    out_lines = [ln for ln in item.material_lines.all() if ln.direction == 'out']
    in_lines = [ln for ln in item.material_lines.all() if ln.direction == 'in']
    return render(request, 'san_xuat/subcontract_detail.html', {
        **_perm_ctx(request),
        'item': item,
        'can_update': can_update,
        'out_lines': out_lines,
        'in_lines': in_lines,
        'receive_form': receive_form,
        'add_out_form': add_out_form,
        'STATUS_SENT': Sub.STATUS_SENT,
        'STATUS_RECEIVED': Sub.STATUS_RECEIVED,
        'STATUS_DONE': Sub.STATUS_DONE,
        'STATUS_CANCELLED': Sub.STATUS_CANCELLED,
        'STATUS_DRAFT': Sub.STATUS_DRAFT,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def piece_rate_report(request):
    from san_xuat.services.overview import parse_overview_period
    from san_xuat.services.phase3 import compute_piece_rate_pay

    date_from, date_to = parse_overview_period(
        month=(request.GET.get('month') or '').strip(),
        date_from=(request.GET.get('date_from') or '').strip(),
        date_to=(request.GET.get('date_to') or '').strip(),
    )
    mo_raw = (request.GET.get('mo') or '').strip()
    mo_id = int(mo_raw) if mo_raw.isdigit() else None
    rows = compute_piece_rate_pay(date_from=date_from, date_to=date_to, production_order_id=mo_id)
    unmapped_count = sum(1 for r in rows if not r.hr_mapped)
    total_amount = sum((r.amount for r in rows), Decimal('0'))
    total_qty = sum((r.qty_good for r in rows), Decimal('0'))
    return render(request, 'san_xuat/piece_rate_report.html', {
        **_perm_ctx(request),
        'rows': rows,
        'date_from': date_from,
        'date_to': date_to,
        'month_value': f'{date_from.year:04d}-{date_from.month:02d}',
        'mo_id': mo_raw,
        'unmapped_count': unmapped_count,
        'total_amount': total_amount,
        'total_qty': total_qty,
    })
