"""Hub Sản xuất — overview, danh sách demo, deep-link redirects."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.menu_permissions import (
    handle_menu_access_denied,
    user_can_access_menu,
    user_can_create_menu,
    user_can_update_menu,
)
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
    SxMoProcessStep,
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
    SxWorkCenter,
)
from san_xuat.models import ProcessStep, ProductTechDoc
from san_xuat.views import _perm_ctx
from san_xuat.forms_costing import CostTypeForm, OrderPlanCostCreateForm, StandardCostSheetCreateForm
from san_xuat.services.plan_methods import (
    bucket_start_for,
    is_bucket_frozen,
    list_open_kv_orders,
    load_mps_demand,
    load_mto_demand,
    load_mts_demand,
    mps_buckets,
    recompute_plan_netting,
    upsert_stock_policy,
)
from san_xuat.services.demand import build_mts_stock_board, build_restock_suggestions
from san_xuat.services.scheduling import (
    check_detail_plan_center_capacity,
    product_routing,
    schedule_detail_plan_by_capacity,
)
from san_xuat.forms_plan import (
    DetailPlanExplodeForm,
    ImportKvOrderForm,
    MaterialPlanExplodeForm,
    MpsLineForm,
    MtoLoadOrdersForm,
    MtsLoadForm,
    NplPurchaseRequestCreateForm,
    OverallPlanCreateForm,
    OverallPlanLineForm,
    PurchaseOrderCreateForm,
    StockPolicyForm,
)
from san_xuat.forms_phase3 import (
    PackingCreateForm,
    PackingLineFormSet,
    SubcontractCreateForm,
    SubcontractMaterialLineForm,
    SubcontractOutLineFormSet,
    SubcontractReceiveForm,
    TraceLookupForm,
    WorkCenterForm,
)
from san_xuat.forms_dispatch import (
    ScheduleMoUpdateForm,
    DisassemblyCreateForm,
    FgReceiptCreateForm,
    FgReceiptLineFormSet,
    FgReceiptLinkKvForm,
    make_fg_receipt_line_formset,
    MaterialIssueApproveForm,
    NplSurplusCreateForm,
    ProductionOrderCreateForm,
    ProductionOrderUpdateForm,
    ProductionStatCreateForm,
    WipHandoverCreateForm,
    WipReturnCreateForm,
    production_stat_initial_from_mo,
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
    assert_user_can_create_stat,
    build_material_issue_request,
    confirm_disassembly_order,
    confirm_npl_surplus,
    confirm_stat,
    create_disassembly_order,
    create_fg_receipt_from_mo,
    fg_receipt_prefill,
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
    user_can_manage_mo_step,
    user_can_stat_mo_step,
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
    assign_detail_plan_work_centers,
    build_overall_lines_from_kv_order,
    build_po_from_purchase_request,
    build_pr_from_material_plan,
    cancel_plan,
    check_detail_plan_capacity,
    close_plan,
    confirm_detail_plan,
    confirm_material_plan,
    confirm_overall_plan,
    confirm_purchase_order,
    create_overall_plan,
    detail_plan_progress,
    explode_detail_plan_from_overall,
    explode_material_plan,
    link_kv_purchase_to_po,
    reject_npl_purchase_request,
    remove_overall_plan_lines,
    resolve_daily_capacity,
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

    from san_xuat.list_filters import resolve_sx_period
    from san_xuat.services.overview import build_overview_dashboard

    month = (request.GET.get('month') or '').strip()
    date_from_raw = (request.GET.get('date_from') or '').strip()
    date_to_raw = (request.GET.get('date_to') or '').strip()
    product_code = (request.GET.get('product_code') or '').strip()
    team_label = (request.GET.get('team_label') or '').strip()
    active_tab = (request.GET.get('tab') or 'tong-hop').strip().lower()
    allowed_tabs = {'tong-hop', 'lenh-sx', 'san-luong', 'chat-luong'}
    if active_tab not in allowed_tabs:
        active_tab = 'tong-hop'
    date_from, date_to, filters = resolve_sx_period(request)
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
        **sx_filter_context(filters),
        'chart_mo_labels_json': _j([row['label'] for row in dash.mo_by_status]),
        'chart_mo_data_json': _j([row['count'] for row in dash.mo_by_status]),
        'chart_day_labels_json': _j([row['label'] for row in dash.production_by_day]),
        'chart_day_good_json': _j([row['qty_good'] for row in dash.production_by_day]),
        'chart_day_defect_json': _j([row['qty_defect'] for row in dash.production_by_day]),
        'chart_qc_data_json': _j([dash.qc_pass, dash.qc_fail, dash.qc_pending]),
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


def _user_can_sales_order_page(user) -> bool:
    """Chi tiết ĐĐH: được vào nếu có bất kỳ menu ĐĐH nào."""
    return (
        user_can_access_menu(user, MODULE_SAN_XUAT, 'orders')
        or user_can_access_menu(user, MODULE_SAN_XUAT, 'order_create')
        or user_can_access_menu(user, MODULE_SAN_XUAT, 'order_confirm')
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def sales_order_list(request):
    """Danh sách đơn đặt hàng sản xuất (SoT Portal)."""
    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, 'orders'):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'orders')

    from san_xuat.hub_models import SxSalesOrder
    from san_xuat.services.sales_orders import (
        PROD_STATUS_LABELS,
        production_status_summary,
    )

    q = (request.GET.get('q') or '').strip()
    confirm = (request.GET.get('confirm') or '').strip()
    qs = SxSalesOrder.objects.filter(is_demo=False).prefetch_related('lines')
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(code__icontains=q)
            | Q(customer_name__icontains=q)
        )
    if confirm in {
        SxSalesOrder.CONFIRM_DRAFT,
        SxSalesOrder.CONFIRM_CONFIRMED,
        SxSalesOrder.CONFIRM_REJECTED,
    }:
        qs = qs.filter(confirm_status=confirm)

    orders = list(qs.order_by('-request_date', '-id')[:300])
    rows = []
    for o in orders:
        st = production_status_summary(o)
        rows.append({
            'order': o,
            'line_count': o.lines.count(),
            'total_qty': sum((ln.qty for ln in o.lines.all()), start=Decimal('0')),
            'prod_status': st,
            'prod_label': PROD_STATUS_LABELS.get(st, st),
        })

    can_create_order = user_can_create_menu(
        request.user, MODULE_SAN_XUAT, 'order_create',
    ) or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'order_create')

    return render(request, 'san_xuat/sales_order_list.html', {
        **_perm_ctx(request),
        'rows': rows,
        'search_query': q,
        'confirm_filter': confirm,
        'can_create_order': can_create_order,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def sales_order_create(request):
    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, 'order_create'):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'order_create')
    if request.method == 'POST' and not (
        user_can_create_menu(request.user, MODULE_SAN_XUAT, 'order_create')
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'order_create')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'order_create')

    from san_xuat.forms_sales_order import SalesOrderHeaderForm, SalesOrderLineFormSet
    from san_xuat.services.sales_orders import LineInput, create_sales_order

    header = SalesOrderHeaderForm(
        request.POST or None,
        request.FILES or None,
        initial={
            'request_date': timezone.localdate(),
            'due_date': timezone.localdate() + timedelta(days=14),
        },
    )
    formset = SalesOrderLineFormSet(request.POST or None, prefix='lines')

    if request.method == 'POST':
        if header.is_valid() and formset.is_valid():
            lines: list[LineInput] = []
            for f in formset:
                if not hasattr(f, 'cleaned_data') or not f.cleaned_data:
                    continue
                if f.cleaned_data.get('DELETE'):
                    continue
                code = (f.cleaned_data.get('product_code') or '').strip()
                qty = f.cleaned_data.get('qty')
                if not code or not qty:
                    continue
                size_raw = f.cleaned_data.get('size_qtys') or '{}'
                try:
                    size_qtys = json.loads(size_raw) if isinstance(size_raw, str) else (size_raw or {})
                except (TypeError, ValueError):
                    size_qtys = {}
                smv_raw = f.cleaned_data.get('applied_smv_json') or '[]'
                try:
                    applied_smv = json.loads(smv_raw) if isinstance(smv_raw, str) else (smv_raw or [])
                except (TypeError, ValueError):
                    applied_smv = []
                if not isinstance(applied_smv, list):
                    applied_smv = []
                bom_raw = f.cleaned_data.get('applied_bom_json') or '[]'
                try:
                    applied_bom = json.loads(bom_raw) if isinstance(bom_raw, str) else (bom_raw or [])
                except (TypeError, ValueError):
                    applied_bom = []
                if not isinstance(applied_bom, list):
                    applied_bom = []
                lines.append(
                    LineInput(
                        product_code=code,
                        product_name=f.cleaned_data.get('product_name') or '',
                        qty=qty,
                        qty_scrap_rate=Decimal('0'),
                        size_qtys=size_qtys if isinstance(size_qtys, dict) else {},
                        bom_version_id=f.cleaned_data.get('bom_version_id'),
                        routing_id=f.cleaned_data.get('routing_id'),
                        applied_smv=applied_smv,
                        applied_bom=applied_bom,
                    )
                )
            try:
                order = create_sales_order(
                    code=header.cleaned_data.get('code') or '',
                    customer_name=header.cleaned_data.get('customer_name') or '',
                    request_date=header.cleaned_data['request_date'],
                    due_date=header.cleaned_data.get('due_date'),
                    notes=header.cleaned_data.get('notes') or '',
                    attachment=header.cleaned_data.get('attachment') or None,
                    lines=lines,
                    user=request.user,
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo đơn {order.code}.')
                return redirect('san_xuat:sales_order_detail', pk=order.pk)
        messages.error(request, 'Không tạo được đơn — kiểm tra lại form.')

    # Size chuẩn công cụ đề xuất SL
    suggest_sizes = ['S', 'M', 'L', 'XL', '2XL', '3XL']
    suggest_sizes_all = [
        '1', '3', '5', '7', '9', '11', '13', '15',
        'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL',
    ]
    u = request.user
    profile = getattr(u, 'profile', None)
    order_creator_label = (
        (getattr(profile, 'full_name', None) or '').strip()
        or (u.get_full_name() or '').strip()
        or u.get_username()
    )
    return render(request, 'san_xuat/sales_order_form.html', {
        **_perm_ctx(request),
        'header': header,
        'formset': formset,
        'is_create': True,
        'order_creator_label': order_creator_label,
        'order_created_at': timezone.localtime(),
        'suggest_sizes': suggest_sizes,
        'suggest_sizes_json': json.dumps(suggest_sizes, ensure_ascii=False),
        'suggest_sizes_all': suggest_sizes_all,
        'suggest_sizes_all_json': json.dumps(suggest_sizes_all, ensure_ascii=False),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def sales_order_confirm_list(request):
    """Hàng đợi xác nhận đơn đặt hàng (nháp)."""
    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, 'order_confirm'):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'order_confirm')

    from san_xuat.forms_sales_order import SalesOrderRejectForm
    from san_xuat.hub_models import SxSalesOrder
    from san_xuat.services.sales_orders import (
        PROD_STATUS_LABELS,
        confirm_sales_order,
        production_status_summary,
        reject_sales_order,
    )

    can_confirm = user_can_update_menu(request.user, MODULE_SAN_XUAT, 'order_confirm')
    reject_form = SalesOrderRejectForm()

    if request.method == 'POST' and can_confirm:
        action = (request.POST.get('action') or '').strip()
        try:
            order_id = int(request.POST.get('order_id') or 0)
        except (TypeError, ValueError):
            order_id = 0
        if order_id and action == 'confirm':
            try:
                order = confirm_sales_order(order_id=order_id, user=request.user)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã xác nhận đơn {order.code}.')
            return redirect('san_xuat:sales_order_confirm_list')
        if order_id and action == 'reject':
            reject_form = SalesOrderRejectForm(request.POST)
            if reject_form.is_valid():
                try:
                    order = reject_sales_order(
                        order_id=order_id,
                        reason=reject_form.cleaned_data.get('reason') or '',
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã từ chối đơn {order.code}.')
                return redirect('san_xuat:sales_order_confirm_list')

    q = (request.GET.get('q') or '').strip()
    qs = SxSalesOrder.objects.filter(
        is_demo=False,
        confirm_status=SxSalesOrder.CONFIRM_DRAFT,
    ).prefetch_related('lines')
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(code__icontains=q)
            | Q(customer_name__icontains=q)
        )

    orders = list(qs.order_by('request_date', 'id')[:300])
    rows = []
    for o in orders:
        st = production_status_summary(o)
        rows.append({
            'order': o,
            'line_count': o.lines.count(),
            'total_qty': sum((ln.qty for ln in o.lines.all()), start=Decimal('0')),
            'prod_status': st,
            'prod_label': PROD_STATUS_LABELS.get(st, st),
        })

    return render(request, 'san_xuat/sales_order_confirm_list.html', {
        **_perm_ctx(request),
        'rows': rows,
        'search_query': q,
        'can_confirm': can_confirm,
        'reject_form': reject_form,
    })


def _so_dec(raw, default='0'):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(raw if raw not in (None, '') else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _handle_order_routing_post(request, order) -> bool:
    """Xử lý POST công đoạn đơn. True = đã handle (redirect caller)."""
    from san_xuat.services.order_routing import (
        OrderRoutingError,
        delete_order_routing_line,
        reset_order_line_routing,
        scale_order_line_applied_smv,
        upsert_order_routing_line,
        user_can_edit_order_routing,
    )

    action = (request.POST.get('action') or '').strip()
    if action not in {
        'add_routing_line', 'edit_routing_line', 'delete_routing_line',
        'reset_routing', 'attach_routing', 'scale_smv',
    }:
        return False
    can_pick = (
        user_can_edit_order_routing(request.user)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'order_create')
        or user_can_create_menu(request.user, MODULE_SAN_XUAT, 'order_create')
    )
    if action == 'attach_routing':
        if not can_pick:
            raise OrderRoutingError('Không có quyền gắn routing trên đơn.')
    elif not user_can_edit_order_routing(request.user):
        raise OrderRoutingError('Chỉ IE / Kế hoạch được sửa SMV áp dụng và thêm/bớt công đoạn trên đơn.')

    def _line():
        try:
            lid = int(request.POST.get('so_line_id') or 0)
        except (TypeError, ValueError):
            lid = 0
        ln = order.lines.filter(pk=lid).first() if lid else None
        if ln is None:
            raise OrderRoutingError('Không tìm thấy dòng sản phẩm.')
        return ln

    if action == 'attach_routing':
        from san_xuat.services.order_routing import attach_order_line_routing

        n = attach_order_line_routing(_line(), routing_id=request.POST.get('routing_id') or 0)
        messages.success(request, f'Đã gắn routing và copy {n} công đoạn lên đơn.')
        return True

    if action == 'reset_routing':
        n = reset_order_line_routing(_line())
        messages.success(request, f'Đã lấy lại {n} công đoạn từ routing mã hàng.')
        return True

    if action == 'scale_smv':
        n = scale_order_line_applied_smv(
            _line(),
            request.POST.get('smv_pct') or 0,
            explanation=request.POST.get('variance_explanation') or '',
        )
        messages.success(request, f'Đã áp SMV đơn cho {n} công đoạn (không đổi SMV chuẩn mã hàng).')
        return True

    if action == 'delete_routing_line':
        ln = _line()
        try:
            line_pk = int(request.POST.get('line_pk') or 0)
        except (TypeError, ValueError):
            line_pk = 0
        if not line_pk:
            raise OrderRoutingError('Thiếu dòng cần xóa.')
        delete_order_routing_line(order_line=ln, line_pk=line_pk)
        messages.success(request, 'Đã xóa công đoạn trên đơn.')
        return True

    ln = _line()
    line_pk = request.POST.get('line_pk')
    line_pk = int(line_pk) if line_pk and str(line_pk).isdigit() else None
    seq_raw = (request.POST.get('seq_no') or '').strip()
    lib_raw = (request.POST.get('library_unit_smv') or '').strip()
    applied_raw = (request.POST.get('applied_unit_smv') or '').strip()
    upsert_order_routing_line(
        order_line=ln,
        line_pk=line_pk if action == 'edit_routing_line' else None,
        seq_no=int(seq_raw) if seq_raw.isdigit() else None,
        op_code=(request.POST.get('op_code') or '').strip(),
        op_rev=(request.POST.get('op_rev') or 'R01').strip(),
        op_name_vi=(request.POST.get('op_name_vi') or '').strip(),
        group_code=(request.POST.get('group_code') or '').strip(),
        qty_per_garment=_so_dec(request.POST.get('qty_per_garment'), '1'),
        applied_unit_smv=_so_dec(applied_raw) if applied_raw else None,
        library_unit_smv=_so_dec(lib_raw) if lib_raw else None,
        machine_code=(request.POST.get('machine_code') or '').strip(),
        work_center_code=(request.POST.get('work_center_code') or '').strip(),
        skill_level_label=(request.POST.get('skill_level_label') or '').strip(),
        price_factor=_so_dec(request.POST.get('price_factor'), '0'),
        total_unit_price=_so_dec(request.POST.get('total_unit_price'), '0'),
        variance_explanation=(request.POST.get('variance_explanation') or '').strip(),
        notes=(request.POST.get('notes') or '').strip(),
    )
    messages.success(request, 'Đã lưu công đoạn trên đơn.')
    return True


@module_perm_required(MODULE_SAN_XUAT, 'view')
def sales_order_detail(request, pk: int):
    if not _user_can_sales_order_page(request.user):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'orders')

    from san_xuat.forms_sales_order import SalesOrderRejectForm
    from san_xuat.hub_models import SxSalesOrder
    from san_xuat.ie_models import SxOperationGroup, ensure_skill_levels_abc
    from san_xuat.services.capacity_from_hrm import hr_work_centers_qs
    from san_xuat.services.order_routing import OrderRoutingError, user_can_edit_order_routing
    from san_xuat.services.sales_orders import (
        PROD_STATUS_LABELS,
        confirm_sales_order,
        production_status_summary,
        reject_sales_order,
    )

    order = get_object_or_404(
        SxSalesOrder.objects.select_related('created_by', 'confirmed_by').prefetch_related(
            'lines__bom_version__tech_doc',
            'lines__routing',
            'lines__routing_lines__work_center',
            'lines__routing_lines__operation',
        ),
        pk=pk,
        is_demo=False,
    )
    can_confirm = user_can_update_menu(request.user, MODULE_SAN_XUAT, 'order_confirm')
    can_edit_routing = user_can_edit_order_routing(request.user)
    can_attach_routing = can_edit_routing or user_can_update_menu(
        request.user, MODULE_SAN_XUAT, 'order_create',
    ) or user_can_create_menu(request.user, MODULE_SAN_XUAT, 'order_create')
    routing_locked = order.confirm_status != SxSalesOrder.CONFIRM_DRAFT
    reject_form = SalesOrderRejectForm()

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if _handle_order_routing_post(request, order):
                return redirect('san_xuat:sales_order_detail', pk=order.pk)
        except OrderRoutingError as exc:
            messages.error(request, str(exc))
            return redirect('san_xuat:sales_order_detail', pk=order.pk)
        if action in {'confirm', 'reject'} and not can_confirm:
            return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'order_confirm')
        if action == 'confirm' and order.confirm_status == SxSalesOrder.CONFIRM_DRAFT:
            try:
                confirm_sales_order(order_id=order.pk, user=request.user)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã xác nhận đơn {order.code}.')
                return redirect('san_xuat:sales_order_detail', pk=order.pk)
        elif action == 'reject':
            reject_form = SalesOrderRejectForm(request.POST)
            if reject_form.is_valid():
                try:
                    reject_sales_order(
                        order_id=order.pk,
                        reason=reject_form.cleaned_data.get('reason') or '',
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã từ chối đơn {order.code}.')
                    return redirect('san_xuat:sales_order_detail', pk=order.pk)

    prod_status = production_status_summary(order)
    edit_rt = None
    edit_pk = (request.GET.get('edit_rt') or '').strip()
    if edit_pk.isdigit() and can_edit_routing and not routing_locked:
        from san_xuat.hub_models import SxSalesOrderRoutingLine
        edit_rt = SxSalesOrderRoutingLine.objects.filter(
            pk=int(edit_pk),
            sales_order_line__order_id=order.pk,
        ).first()

    from san_xuat.services.order_routing import routings_for_product

    for ln in order.lines.all():
        ln.available_routings = routings_for_product(ln.product_code) if not ln.routing_id else []

    return render(request, 'san_xuat/sales_order_detail.html', {
        **_perm_ctx(request),
        'order': order,
        'can_confirm': can_confirm,
        'can_edit_order_routing': False,
        'can_attach_routing': False,
        'routing_locked': routing_locked,
        'edit_rt': edit_rt,
        'work_centers': list(hr_work_centers_qs()),
        'skill_levels': ensure_skill_levels_abc(),
        'operation_groups': list(
            SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code')
        ),
        'reject_form': reject_form,
        'prod_status': prod_status,
        'prod_label': PROD_STATUS_LABELS.get(prod_status, prod_status),
    })


# backward-compatible name (menu cũ)
redirect_orders = sales_order_list


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
    kho_sp_count = 0
    try:
        from kho_san_pham.models import Product
        kho_sp_count = Product.objects.filter(is_active=True).count()
    except Exception:
        pass
    return render(request, 'san_xuat/hub_products_nvl.html', {
        **_perm_ctx(request),
        'doc_total': docs.count(),
        'doc_active': docs.filter(is_active=True).count(),
        'bom_active': BomVersion.objects.filter(status=BomVersion.STATUS_ACTIVE).count(),
        'material_active': Material.objects.filter(is_active=True).count()
        if hasattr(Material, 'is_active') else Material.objects.count(),
        'kho_sp_count': kho_sp_count,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_norm(request):
    from san_xuat.list_grid import sx_list_grid_context

    filters = parse_sx_list_filters(request)
    rows = filter_tuple_rows(
        list_costing_from_active_boms(),
        filters,
        date_index=1,
        date_attr='updated_at',
    )
    return render(request, 'san_xuat/costing_bom_list.html', {
        **_perm_ctx(request),
        'rows': rows,
        'product_count': len(rows),
        **sx_filter_context(filters),
        **sx_list_grid_context(request, 'costing_bom'),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_sheet_list(request):
    base_qs = (
        SxStandardCostSheet.objects.filter(is_demo=False)
        .prefetch_related('lines')
        .order_by('-date_from', '-pk')
    )
    sheets, fctx = prepare_hub_list(request, base_qs, SX_FILTER_COST_SHEET, list_key='costing_sheet')
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
    sheets, fctx = prepare_hub_list(request, base_qs, SX_FILTER_COST_ORDER, list_key='costing_order')
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


@module_perm_required(MODULE_SAN_XUAT, 'export')
def costing_order_export(request, pk: int):
    sheet = get_object_or_404(
        SxOrderPlanCost.objects.prefetch_related('lines__typed_extras__cost_type'),
        pk=pk,
    )
    return export_order_plan_cost_xlsx(sheet=sheet)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_cost_types(request):
    base_qs = SxCostType.objects.filter(is_demo=False).order_by('sort_order', 'code')
    cost_types, fctx = prepare_hub_list(request, base_qs, SX_FILTER_COST_TYPE, list_key='costing_cost_type')
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
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_board(request):
    """Kế hoạch SX theo đơn — hàng đợi / đã chuyển SX."""
    from san_xuat.hub_models import SxSalesOrder
    from san_xuat.services.plan_board import (
        PLAN_STATUS_LABELS,
        PRIORITY_LABELS,
        QUEUE_STATUSES,
        build_plan_board_rows,
        confirmed_order_qty_summary,
        hold_plan_order,
        pipeline_counts,
        release_order_to_production,
        set_plan_priority,
        sync_plan_status,
        unhold_plan_order,
    )
    from san_xuat.services.planning import PlanningError

    menu_key = 'plan_board'
    if not (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, menu_key)

    can_schedule = (
        user_can_update_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'plan')
    )
    can_release = (
        user_can_create_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'plan')
    )

    mode = (request.GET.get('mode') or request.POST.get('mode') or 'list').strip()
    if mode == 'route':
        return redirect('san_xuat:plan_route')
    mode = 'list'

    tab = (request.GET.get('tab') or 'queue').strip()
    if tab == 'load':
        from urllib.parse import urlencode
        params = {'mode': 'list', 'tab': 'queue'}
        if q_early := (request.GET.get('q') or '').strip():
            params['q'] = q_early
        return redirect(f"{reverse('san_xuat:plan_board')}?{urlencode(params)}")
    if tab not in {'queue', 'released'}:
        tab = 'queue'
    q = (request.GET.get('q') or request.POST.get('q') or '').strip()

    def _board_redirect(**extra):
        params = {'mode': mode, 'tab': tab}
        if q:
            params['q'] = q
        params.update(extra)
        from urllib.parse import urlencode
        return redirect(f"{reverse('san_xuat:plan_board')}?{urlencode(params)}")

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            order_id = int(request.POST.get('order_id') or 0)
        except (TypeError, ValueError):
            order_id = 0

        try:
            if action == 'set_priority' and can_schedule and order_id:
                set_plan_priority(
                    order_id=order_id,
                    priority=(request.POST.get('priority') or '').strip(),
                )
                messages.success(request, 'Đã cập nhật ưu tiên.')
            elif action == 'hold' and can_schedule and order_id:
                hold_plan_order(
                    order_id=order_id,
                    reason=(request.POST.get('reason') or '').strip(),
                )
                messages.success(request, 'Đã tạm giữ đơn trên hàng đợi.')
            elif action == 'unhold' and can_schedule and order_id:
                unhold_plan_order(order_id=order_id)
                messages.success(request, 'Đã bỏ giữ — đơn về chờ xếp.')
            elif action == 'release' and can_release and order_id:
                bom_by_product: dict[str, int] = {}
                routing_by_product: dict[str, int] = {}
                for key, val in request.POST.items():
                    raw = (val or '').strip()
                    if key.startswith('bom_for__'):
                        code = key[len('bom_for__'):].strip()
                        if code and raw.isdigit():
                            bom_by_product[code] = int(raw)
                    elif key.startswith('routing_for__'):
                        code = key[len('routing_for__'):].strip()
                        if code and raw.isdigit():
                            routing_by_product[code] = int(raw)
                created = release_order_to_production(
                    order_id=order_id,
                    user=request.user,
                    bom_by_product=bom_by_product,
                    routing_by_product=routing_by_product,
                )
                messages.success(
                    request,
                    f'Đã chuyển xuống SX — tạo {len(created)} lệnh sản xuất (đã phát hành vào Công việc tổ).',
                )
                return redirect(f"{reverse('san_xuat:plan_board')}?mode=list&tab=released")
            else:
                if action:
                    messages.error(request, 'Bạn không có quyền thực hiện thao tác này.')
        except PlanningError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, str(exc))
        return _board_redirect()

    counts = pipeline_counts()
    qty_summary = confirmed_order_qty_summary()
    queue_rows = []
    released_rows = []

    if tab == 'queue':
        queue_rows = build_plan_board_rows(statuses=QUEUE_STATUSES, search=q)
    else:
        released_rows = build_plan_board_rows(
            statuses=(
                SxSalesOrder.PLAN_RELEASED,
                SxSalesOrder.PLAN_IN_PROGRESS,
                SxSalesOrder.PLAN_DONE,
            ),
            search=q,
            include_released=True,
        )
        for row in released_rows:
            sync_plan_status(row.order)

    return render(request, 'san_xuat/plan_board.html', {
        **_perm_ctx(request),
        'mode': mode,
        'tab': tab,
        'search_query': q,
        'counts': counts,
        'qty_summary': qty_summary,
        'queue_rows': queue_rows,
        'released_rows': released_rows,
        'can_schedule': can_schedule,
        'can_release': can_release,
        'plan_status_labels': PLAN_STATUS_LABELS,
        'priority_labels': PRIORITY_LABELS,
        'priority_choices': SxSalesOrder.PRIORITY_CHOICES,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_route(request):
    """Lộ trình sản xuất — timeline theo ngày bắt đầu / kết thúc dự kiến của LSX."""
    from calendar import monthrange
    from datetime import date as date_cls

    from san_xuat.list_filters import date_range_span_context, parse_sx_date
    from san_xuat.services.plan_board import _monday_on_or_before, build_mo_timeline

    menu_key = 'plan_route'
    if not (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan_board')
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, menu_key)

    raw_from = (request.GET.get('date_from') or request.GET.get('from') or '').strip()
    raw_to = (request.GET.get('date_to') or '').strip()
    month = (request.GET.get('month') or '').strip()
    range_from = parse_sx_date(raw_from)
    range_to = parse_sx_date(raw_to)
    if not range_from and not range_to and month:
        try:
            y, m = month.split('-', 1)
            year, mon = int(y), int(m)
            last = monthrange(year, mon)[1]
            range_from = date_cls(year, mon, 1)
            range_to = date_cls(year, mon, last)
        except (ValueError, IndexError):
            pass

    q = (request.GET.get('q') or '').strip()
    board = build_mo_timeline(
        range_from=range_from,
        range_to=range_to,
        search=q,
    )
    today_start = _monday_on_or_before(board.today)
    has_filters = bool(raw_from or raw_to or month or q or request.GET.get('span'))
    return render(request, 'san_xuat/plan_route.html', {
        **_perm_ctx(request),
        'board': board,
        'today_monday': today_start,
        'today_end': today_start + timedelta(days=27),
        'has_filters': has_filters,
        'month_value': f'{board.range_start.year:04d}-{board.range_start.month:02d}',
        **date_range_span_context(board.range_start, board.range_end),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_progress_monitor(request):
    """Đã gộp vào bảng kế hoạch SX (tab Đã chuyển SX)."""
    return redirect(f"{reverse('san_xuat:plan_board')}?tab=released")


@module_perm_required(MODULE_SAN_XUAT, 'view')
def order_progress_sheet(request, mo_id: int):
    """Phiếu theo dõi tiến độ ra hàng — size × công đoạn mẫu cố định."""
    from datetime import date as date_cls
    from decimal import Decimal, InvalidOperation

    from san_xuat.hub_models import SxProductionOrder
    from san_xuat.services.order_progress_sheet import (
        build_progress_sheet,
        ensure_progress_work_centers,
        record_progress_qty,
    )
    from san_xuat.services.planning import PlanningError
    from san_xuat.services.progress_template import progress_steps

    menu_key = 'plan_board'
    if not (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'plan')
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'dispatch_mo')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, menu_key)

    can_update = (
        user_can_update_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'plan')
        or user_can_create_menu(request.user, MODULE_SAN_XUAT, menu_key)
    )

    mo = (
        SxProductionOrder.objects.filter(pk=mo_id, is_demo=False)
        .select_related('sales_order')
        .first()
    )
    if not mo:
        messages.error(request, 'Không tìm thấy lệnh sản xuất.')
        return redirect('san_xuat:plan_board')

    ensure_progress_work_centers()

    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        if action == 'record':
            try:
                qty = Decimal(str(request.POST.get('qty') or '0').replace(',', '').strip() or '0')
            except (InvalidOperation, ValueError):
                qty = Decimal('0')
            raw_date = (request.POST.get('stat_date') or '').strip()
            try:
                stat_date = date_cls.fromisoformat(raw_date) if raw_date else None
            except ValueError:
                stat_date = None
            try:
                record_progress_qty(
                    mo_id=mo.pk,
                    process_key=(request.POST.get('process_key') or '').strip(),
                    size_label=(request.POST.get('size_label') or '').strip(),
                    qty=qty,
                    stat_date=stat_date,
                    user=request.user,
                )
                messages.success(request, 'Đã ghi SL tiến độ.')
            except PlanningError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect('san_xuat:order_progress_sheet', mo_id=mo.pk)

    sheet = build_progress_sheet(mo)
    flat_steps = progress_steps()

    return render(request, 'san_xuat/order_progress_sheet.html', {
        **_perm_ctx(request),
        'mo': mo,
        'sheet': sheet,
        'flat_steps': flat_steps,
        'can_update': can_update,
        'today': timezone.localdate(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall(request):
    """Đã gộp vào bảng kế hoạch SX theo đơn — URL cũ redirect."""
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall_create(request):
    """Đã gộp vào bảng kế hoạch SX theo đơn — URL cũ redirect."""
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall_detail(request, pk: int):
    """Đã gộp vào bảng kế hoạch SX theo đơn — URL cũ redirect."""
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def stock_policy_list(request):
    """Chính sách tồn thành phẩm — nền cho phương án MTS."""
    from san_xuat.hub_models import SxProductStockPolicy

    can_update = _perm_ctx(request).get('can_update')
    form = StockPolicyForm()

    if request.method == 'POST' and can_update:
        action = (request.POST.get('action') or '').strip()
        if action == 'delete':
            pk = (request.POST.get('pk') or '').strip()
            if pk.isdigit():
                SxProductStockPolicy.objects.filter(pk=int(pk)).delete()
                messages.success(request, 'Đã xóa chính sách tồn.')
            return redirect('san_xuat:stock_policy_list')
        form = StockPolicyForm(request.POST)
        if form.is_valid():
            try:
                policy = upsert_stock_policy(
                    product_code=form.cleaned_data['product_code'],
                    product_name=form.cleaned_data.get('product_name') or '',
                    min_stock=form.cleaned_data['min_stock'],
                    max_stock=form.cleaned_data.get('max_stock'),
                    lead_time_days=form.cleaned_data.get('lead_time_days') or 0,
                    is_active=form.cleaned_data.get('is_active', True),
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã lưu chính sách tồn cho {policy.product_code}.')
                return redirect('san_xuat:stock_policy_list')
        else:
            messages.error(request, 'Không lưu được — kiểm tra lại form.')

    search = (request.GET.get('q') or '').strip()
    qs = SxProductStockPolicy.objects.filter(is_demo=False)
    if search:
        from django.db.models import Q

        qs = qs.filter(Q(product_code__icontains=search) | Q(product_name__icontains=search))
    policies = list(qs.order_by('product_code'))

    suggestions = build_restock_suggestions(include_covered=True)
    by_code = {s.policy.pk: s for s in suggestions}
    rows = [{'policy': p, 'stat': by_code.get(p.pk)} for p in policies]
    need_count = sum(1 for s in suggestions if s.qty_suggest > 0)

    return render(request, 'san_xuat/stock_policy_list.html', {
        **_perm_ctx(request),
        'rows': rows,
        'form': form,
        'can_update': can_update,
        'search_query': search,
        'total_count': len(policies),
        'need_count': need_count,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def restock_suggestions(request):
    """Đề xuất sản xuất bù tồn — có thể tạo KHTT (MTS) trực tiếp."""
    can_create = _perm_ctx(request).get('can_create')
    rows = build_restock_suggestions()

    if request.method == 'POST' and can_create:
        codes = [c for c in request.POST.getlist('product_codes') if (c or '').strip()]
        if not codes:
            messages.error(request, 'Chưa chọn mã sản phẩm nào.')
            return redirect('san_xuat:restock_suggestions')
        today = timezone.localdate()
        span = 6
        try:
            plan = create_overall_plan(
                name=f'Bù tồn {today:%d/%m/%Y}',
                date_from=today,
                date_to=today + timedelta(days=span),
                plan_method=SxOverallPlan.METHOD_MTS,
                apply_netting=True,
                user=request.user,
            )
            load_mts_demand(plan_id=plan.pk, product_codes=codes, replace=True)
        except PlanningError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f'Đã ghi nhu cầu bù tồn ({len(codes)} mã, mã nội bộ {plan.code}). '
                f'Tiếp theo dùng Kế hoạch NPL nếu cần explode vật tư.',
            )
            return redirect('san_xuat:plan_board')

    return render(request, 'san_xuat/restock_suggestions.html', {
        **_perm_ctx(request),
        'rows': rows,
        'can_create': can_create,
        'total_suggest': sum((r.qty_suggest for r in rows), Decimal('0')),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail(request):
    """Đã gộp vào bảng kế hoạch SX theo đơn — URL cũ redirect."""
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail_create(request):
    """Đã gộp vào bảng kế hoạch SX theo đơn — URL cũ redirect."""
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail_detail(request, pk: int):
    """Đã gộp vào bảng kế hoạch SX theo đơn — URL cũ redirect."""
    return redirect('san_xuat:plan_board')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_npl(request):
    base_qs = (
        SxMaterialPlan.objects.filter(is_demo=False)
        .select_related('overall_plan')
        .prefetch_related('lines')
        .order_by('-created_at', '-pk')
    )
    plans, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PLAN_NPL, list_key='plan_npl')
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
                    user=request.user,
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tính kế hoạch NPL {mat_plan.code} ({mat_plan.lines.count()} dòng NVL).')
                return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
        messages.error(request, 'Không tạo được kế hoạch NPL — kiểm tra lại form.')
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
                mat_plan = confirm_material_plan(plan_id=mat_plan.pk, user=request.user)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Kế hoạch NPL {mat_plan.code} đã xác nhận.')
                return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
        elif action == 'refresh' and can_update:
            if not mat_plan.overall_plan_id:
                messages.error(request, 'Kế hoạch NPL không gắn kế hoạch tổng thể nguồn.')
            else:
                try:
                    mat_plan = explode_material_plan(
                        overall_plan_id=mat_plan.overall_plan_id, user=request.user,
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(request, f'Đã cập nhật tồn/shortfall cho kế hoạch NPL {mat_plan.code}.')
                    return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
        elif action == 'close' and can_update:
            try:
                mat_plan = close_plan(model=SxMaterialPlan, plan_id=mat_plan.pk, user=request.user)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã đóng kế hoạch NPL {mat_plan.code}.')
                return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
        elif action == 'cancel' and can_update:
            try:
                mat_plan = cancel_plan(
                    model=SxMaterialPlan,
                    plan_id=mat_plan.pk,
                    reason=request.POST.get('reason') or '',
                    user=request.user,
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã hủy kế hoạch NPL {mat_plan.code} và giải phóng giữ chỗ.')
                return redirect('san_xuat:plan_npl_detail', pk=mat_plan.pk)
    lines_all = list(mat_plan.lines.all())
    shortfall_total = sum((line.qty_shortfall or 0 for line in lines_all), Decimal('0'))
    reserved_total = sum((line.qty_reserved or 0 for line in lines_all), Decimal('0'))
    purchase_requests = mat_plan.purchase_requests.filter(is_demo=False).order_by('-created_at')
    need_dates = [line.need_date for line in lines_all if line.need_date]

    from san_xuat.services.planning import npl_prep_days

    return render(request, 'san_xuat/plan_npl_detail.html', {
        **_perm_ctx(request),
        'mat_plan': mat_plan,
        'can_update': can_update,
        'shortfall_total': shortfall_total,
        'reserved_total': reserved_total,
        'purchase_requests': purchase_requests,
        'earliest_need': min(need_dates) if need_dates else None,
        'prep_days': npl_prep_days(),
        'today': timezone.localdate(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_purchase_request(request):
    base_qs = (
        SxNplPurchaseRequest.objects.filter(is_demo=False)
        .select_related('material_plan', 'material_plan__overall_plan')
        .prefetch_related('lines')
        .order_by('-created_at', '-pk')
    )
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_NPL_PR, list_key='npl_purchase_request')
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
                    user=request.user,
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo yêu cầu mua NPL {pr.code} ({pr.lines.count()} dòng NVL).')
                return redirect('san_xuat:npl_purchase_request_detail', pk=pr.pk)
        messages.error(request, 'Không tạo được yêu cầu mua NPL — kiểm tra lại form.')
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
                messages.success(request, f'Yêu cầu mua NPL {pr.code} đã gửi duyệt.')
                return redirect('san_xuat:npl_purchase_request_detail', pk=pr.pk)
        elif action == 'approve' and can_update and pr.status == SxNplPurchaseRequest.STATUS_SUBMITTED:
            try:
                pr = approve_npl_purchase_request(request_id=pr.pk)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Yêu cầu mua NPL {pr.code} đã duyệt.')
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
                messages.success(request, f'Yêu cầu mua NPL {pr.code} đã từ chối.')
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
    orders, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PURCHASE_ORDER, list_key='purchase_order')
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
                    supplier=form.cleaned_data.get('supplier'),
                    expected_date=form.cleaned_data.get('expected_date'),
                    code=form.cleaned_data.get('code') or None,
                    notes=form.cleaned_data.get('notes') or '',
                    user=request.user,
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo đơn mua hàng {po.code} ({po.lines.count()} dòng NVL).')
                return redirect('san_xuat:purchase_order_detail', pk=po.pk)
        messages.error(request, 'Không tạo được đơn mua hàng — kiểm tra lại form.')
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
    from san_xuat.forms_plan import PoReceiptForm
    from san_xuat.services.po_receipt import (
        create_receipt_from_po,
        po_receipts,
        sync_po_received_from_po_receipts,
    )

    po = get_object_or_404(
        SxPurchaseOrder.objects.select_related(
            'purchase_request',
            'purchase_request__material_plan',
            'supplier',
            'stock_receipt',
        ).prefetch_related('lines'),
        pk=pk,
    )
    can_update = _perm_ctx(request).get('can_update')
    link_form = FgReceiptLinkKvForm()
    receipt_form = PoReceiptForm()
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'confirm' and can_update and po.status == SxPurchaseOrder.STATUS_DRAFT:
            try:
                po = confirm_purchase_order(order_id=po.pk, user=request.user)
            except PlanningError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đơn mua hàng {po.code} đã xác nhận.')
                return redirect('san_xuat:purchase_order_detail', pk=po.pk)
        elif action == 'create_receipt' and can_update:
            receipt_form = PoReceiptForm(request.POST)
            if receipt_form.is_valid():
                try:
                    receipt = create_receipt_from_po(
                        order_id=po.pk,
                        user=request.user,
                        receipt_date=receipt_form.cleaned_data.get('receipt_date'),
                        location=receipt_form.cleaned_data.get('location'),
                        notes=receipt_form.cleaned_data.get('notes') or '',
                    )
                except PlanningError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f'Đã tạo phiếu nhập kho {receipt.number}. '
                        'Vào Kho NPL đính kèm chứng từ rồi ghi sổ để cộng tồn.',
                    )
                    return redirect('san_xuat:purchase_order_detail', pk=po.pk)
            else:
                messages.error(request, 'Không tạo được phiếu nhập — kiểm tra lại thông tin.')
        elif action == 'sync_receipt' and can_update:
            result = sync_po_received_from_po_receipts(order_id=po.pk, user=request.user)
            if result['receipts'] == 0:
                messages.info(request, 'Chưa có phiếu nhập kho nào được ghi sổ cho đơn mua hàng này.')
            elif result['updated'] or result['status_changed']:
                messages.success(
                    request,
                    f"Đã cập nhật {result['updated']} dòng từ {result['receipts']} phiếu nhập"
                    + (' — đơn mua hàng đã nhập đủ.' if result['received_full'] else '.'),
                )
            else:
                messages.info(request, 'Số lượng đã nhập không thay đổi.')
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
    lines_all = list(po.lines.all())
    total_amount = sum((ln.amount for ln in lines_all), Decimal('0'))
    remaining_qty = sum((ln.qty_remaining for ln in lines_all), Decimal('0'))
    lines_without_price = [ln.material_code for ln in lines_all if (ln.unit_price or 0) <= 0]
    return render(request, 'san_xuat/purchase_order_detail.html', {
        **_perm_ctx(request),
        'po': po,
        'can_update': can_update,
        'link_form': link_form,
        'receipt_form': receipt_form,
        'stock_receipts': po_receipts(po),
        'total_amount': total_amount,
        'remaining_qty': remaining_qty,
        'lines_without_price': lines_without_price,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_stub(request):
    from san_xuat.services.mo_progress import pending_material_issue_qs
    from san_xuat.services.sx_settings import sx_bool

    pending_ycx = pending_material_issue_qs().count()
    return render(request, 'san_xuat/hub_dispatch.html', {
        **_perm_ctx(request),
        'pending_ycx_count': pending_ycx,
        'show_pending_ycx_banner': sx_bool('show_pending_ycx_banner', True),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo(request):
    base_qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .order_by('-order_date', '-pk')
        .select_related('bom_version')
    )
    orders, fctx = prepare_hub_list(request, base_qs, SX_FILTER_MO, list_key='dispatch_mo')
    return render(request, 'san_xuat/dispatch_mo_list.html', {
        **_perm_ctx(request),
        'page_title': 'Lệnh sản xuất',
        'orders': orders,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_mo_create(request):
    from san_xuat.services.dispatch import (
        format_mo_line_qty,
        parse_mo_lines_from_post,
        parse_mo_process_steps_from_post,
    )

    lines: list = []
    process_steps = None
    if request.method == 'POST':
        form = ProductionOrderCreateForm(request.POST)
        lines = parse_mo_lines_from_post(request.POST)
        process_steps = parse_mo_process_steps_from_post(request.POST)
        if form.is_valid():
            try:
                mo = create_mo_from_bom(
                    product_code=form.cleaned_data['product_code'],
                    qty=form.cleaned_data.get('qty'),
                    order_date=form.cleaned_data.get('order_date') or timezone.localdate(),
                    due_date=form.cleaned_data.get('due_date'),
                    planned_start=form.cleaned_data.get('planned_start'),
                    planned_end=form.cleaned_data.get('planned_end'),
                    team_label=form.cleaned_data.get('team_label') or '',
                    process_name=form.cleaned_data.get('process_name') or '',
                    notes=form.cleaned_data.get('notes') or '',
                    user=request.user,
                    is_sample=bool(form.cleaned_data.get('is_sample')),
                    lines=lines,
                    bom_version_id=form.cleaned_data.get('bom_version'),
                    process_steps=process_steps,
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo lệnh sản xuất {mo.code}.')
                return redirect('san_xuat:dispatch_mo_detail', pk=mo.pk)
        else:
            messages.error(request, 'Không tạo được lệnh sản xuất — kiểm tra lại form.')
    else:
        initial = {'order_date': timezone.localdate()}
        prefill = (
            (request.GET.get('product') or request.GET.get('code') or request.GET.get('product_code') or '')
            .strip()
        )
        if prefill:
            initial['product_code'] = prefill
        form = ProductionOrderCreateForm(initial=initial)

    from san_xuat.forms_dispatch import mo_manager_options_with_team_defaults
    from san_xuat.services.capacity_from_hrm import work_center_options_with_default_manager

    team_options = work_center_options_with_default_manager()
    mo_line_qty_json = json.dumps({
        f'{(ln.get("color_code") or "").upper()}||{(ln.get("size_label") or "").upper()}': format_mo_line_qty(ln.get("qty"))
        for ln in lines
        if (ln.get("color_code") or "").strip() and (ln.get("size_label") or "").strip()
        and format_mo_line_qty(ln.get("qty"))
    })

    return render(request, 'san_xuat/dispatch_mo_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mode': 'create',
        'team_options_json': json.dumps(team_options, ensure_ascii=False),
        'manager_options_json': json.dumps(
            mo_manager_options_with_team_defaults(team_options), ensure_ascii=False,
        ),
        'mo_line_qty_json': mo_line_qty_json,
        'posted_steps_json': json.dumps(process_steps or [], ensure_ascii=False),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def run_order_wizard(request, mo_id: int | None = None):
    """Wizard đã bỏ — bookmark cũ chuyển về lệnh sản xuất."""
    if mo_id:
        return redirect('san_xuat:dispatch_mo_detail', pk=mo_id)
    return redirect('san_xuat:dispatch_mo')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo_detail(request, pk: int):
    mo = (
        SxProductionOrder.objects.select_related('bom_version__tech_doc', 'bom_version__routing', 'routing')
        .prefetch_related('bom_version__lines__material', 'bom_version__process_steps__work_center', 'lines')
        .get(pk=pk)
    )
    can_update = _perm_ctx(request).get('can_update')
    update_form = None

    # Handle actions
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'save' and mo.status == SxProductionOrder.STATUS_DRAFT and can_update:
            from san_xuat.services.dispatch import (
                parse_mo_lines_from_post,
                parse_mo_process_steps_from_post,
                update_draft_mo,
            )

            form = ProductionOrderUpdateForm(request.POST, bom=mo.bom_version)
            lines = parse_mo_lines_from_post(request.POST)
            process_steps = parse_mo_process_steps_from_post(request.POST)
            if form.is_valid():
                try:
                    update_draft_mo(
                        mo=mo,
                        qty=form.cleaned_data.get('qty'),
                        due_date=form.cleaned_data.get('due_date'),
                        planned_start=form.cleaned_data.get('planned_start'),
                        planned_end=form.cleaned_data.get('planned_end'),
                        team_label=form.cleaned_data.get('team_label') or '',
                        process_name=form.cleaned_data.get('process_name') or '',
                        notes=form.cleaned_data.get('notes') or '',
                        lines=lines,
                        process_steps=process_steps,
                        user=request.user,
                    )
                except DispatchError as exc:
                    messages.error(request, str(exc))
                    update_form = form
                else:
                    messages.success(request, 'Đã lưu lệnh sản xuất.')
                    return redirect('san_xuat:dispatch_mo_detail', pk=mo.pk)
            else:
                messages.error(request, 'Không lưu được lệnh sản xuất — kiểm tra lại form.')
                update_form = form
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

    if update_form is None:
        update_form = ProductionOrderUpdateForm(
            bom=mo.bom_version,
            initial={
                'qty': mo.qty,
                'due_date': mo.due_date,
                'planned_start': mo.planned_start,
                'planned_end': mo.planned_end,
                'team_label': mo.team_label,
                'process_name': mo.process_name,
                'notes': mo.notes,
            },
        )

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
    from san_xuat.services.handover_status import build_mo_handover_row

    handover_row = build_mo_handover_row(mo)

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
    mo_lines = list(mo.lines.all())
    import json
    from san_xuat.services.dispatch import format_mo_line_qty

    mo_line_qty_json = json.dumps({
        f'{(ln.color_code or "").upper()}||{(ln.size_label or "").upper()}': format_mo_line_qty(ln.qty)
        for ln in mo_lines
        if (ln.color_code or "").strip() and (ln.size_label or "").strip()
        and format_mo_line_qty(ln.qty)
    })
    from san_xuat.forms_dispatch import mo_manager_options_with_team_defaults
    from san_xuat.services.capacity_from_hrm import (
        default_manager_user_id_for_work_center,
        mo_form_work_center_id,
        work_center_options_with_default_manager,
    )

    team_options = work_center_options_with_default_manager()
    default_mgr_by_wc = {
        t['id']: t['default_manager_id']
        for t in team_options
        if t.get('default_manager_id')
    }
    mo_process_steps = []
    # Ưu tiên snapshot LSX (có manager); fallback BOM
    mo_steps_qs = list(
        mo.mo_process_steps.select_related('work_center', 'manager', 'manager__profile')
        .order_by('sequence', 'id')[:80]
    )
    if mo_steps_qs:
        for s in mo_steps_qs:
            mgr_label = ''
            if s.manager_id:
                p = getattr(s.manager, 'profile', None)
                mgr_label = (
                    (getattr(p, 'full_name', None) or '') if p else ''
                ).strip() or (s.manager.get_full_name() or s.manager.username)
            mo_process_steps.append({
                'id': s.bom_process_step_id or '',
                'mo_step_id': s.pk,
                'sequence': s.sequence,
                'process_name': s.process_name,
                'work_center_id': s.work_center_id,
                'team_label': s.team_label,
                'manager_id': s.manager_id or '',
                'manager_label': mgr_label,
            })
    elif mo.bom_version_id:
        for s in mo.bom_version.process_steps.select_related('work_center').order_by('sequence', 'id')[:80]:
            wc_id = mo_form_work_center_id(
                work_center=s.work_center,
                work_center_id=s.work_center_id,
                work_center_code=(s.work_center.code if s.work_center_id else '') or '',
                name_hint=s.process_name or '',
            ) or s.work_center_id
            mgr_id = default_mgr_by_wc.get(wc_id) or ''
            if not mgr_id and wc_id:
                mgr_id = default_manager_user_id_for_work_center(wc_id) or ''
            mo_process_steps.append({
                'id': s.pk,
                'sequence': s.sequence,
                'process_name': s.process_name,
                'work_center_id': wc_id,
                'team_label': (
                    (s.work_center.team_label or s.work_center.name)
                    if s.work_center_id else ''
                ),
                'manager_id': mgr_id,
                'manager_label': '',
            })

    return render(request, 'san_xuat/dispatch_mo_detail.html', {
        **_perm_ctx(request),
        'mo': mo,
        'mo_lines': mo_lines,
        'mo_line_qty_json': mo_line_qty_json,
        'update_form': update_form,
        'can_update': can_update,
        'ycx_list': ycx_list,
        'stats_list': stats_list,
        'qc_alerts': qc_alerts,
        'fg_receipt_list': fg_receipt_list,
        'wip_handover_list': wip_handover_list,
        'handover_row': handover_row,
        'bom_lines': bom_lines,
        'progress': progress,
        'team_options_json': json.dumps(team_options, ensure_ascii=False),
        'manager_options_json': json.dumps(
            mo_manager_options_with_team_defaults(team_options), ensure_ascii=False,
        ),
        'mo_process_steps_json': json.dumps(mo_process_steps, ensure_ascii=False),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_disassembly(request):
    base_qs = (
        SxDisassemblyOrder.objects.filter(is_demo=False)
        .select_related('production_order')
        .order_by('-order_date', '-pk')
    )
    orders, fctx = prepare_hub_list(request, base_qs, SX_FILTER_DISASSEMBLY, list_key='disassembly')
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
                messages.success(request, f'Đã tạo lệnh tháo dỡ {order.code}.')
                return redirect('san_xuat:dispatch_disassembly_detail', pk=order.pk)
        messages.error(request, 'Không tạo được lệnh tháo dỡ — kiểm tra lại form.')
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
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_MATERIAL_ISSUE, list_key='dispatch_material_issue')
    return render(request, 'san_xuat/dispatch_material_issue_req_list.html', {
        **_perm_ctx(request),
        'page_title': 'Yêu cầu xuất vật tư',
        'requests': requests_qs,
        'pending_ycx_count': pending_count,
        'queue_pending': queue in ('pending', 'cho-duyet', '1'),
        **fctx,
    })


def _ycx_detail_context(req):
    from decimal import Decimal

    from kho_npl.models import StockBalance, WarehouseLocation

    locations = list(WarehouseLocation.objects.filter(is_active=True).order_by('code')[:200])
    line_rows = []
    has_remaining = False
    for line in req.lines.select_related('preferred_location').all():
        balances = []
        mat = None
        stock_total = Decimal('0')
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
            stock_total = sum((b.quantity for b in balances), Decimal('0'))
        qty_req = line.qty_requested or Decimal('0')
        qty_iss = line.qty_issued or Decimal('0')
        remaining = qty_req - qty_iss
        if remaining < 0:
            remaining = Decimal('0')
        if remaining > 0:
            has_remaining = True
        short = remaining > 0 and stock_total < remaining
        shortfall = (remaining - stock_total) if short else Decimal('0')
        if shortfall < 0:
            shortfall = Decimal('0')
        line_rows.append({
            'line': line,
            'balances': balances,
            'stock_total': stock_total,
            'remaining': remaining,
            'short': short,
            'shortfall': shortfall,
        })
    return {
        'locations': locations,
        'line_rows': line_rows,
        'ycx_has_remaining': has_remaining,
    }


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
        ycx_editable_loc = can_update and req.status in (
            'draft', 'submitted', 'approved', 'partial',
        ) and (
            not req.stock_issue_id
            or req.status == 'partial'
            or getattr(req.stock_issue, 'status', '') == 'draft'
        )
        if action == 'save_locations' and ycx_editable_loc:
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

        if action in ('approve', 'approve_partial') and can_update and req.status in (
            'draft', 'submitted', 'approved', 'partial',
        ):
            form = MaterialIssueApproveForm(request.POST, request.FILES)
            if form.is_valid():
                allow_partial = action == 'approve_partial'
                try:
                    res = approve_material_issue(
                        request_id=req.pk,
                        user=request.user,
                        attachment=form.cleaned_data.get('attachment') or None,
                        allow_partial=allow_partial,
                    )
                except DispatchError as exc:
                    messages.error(request, str(exc))
                else:
                    if res.request.status == 'partial':
                        messages.success(
                            request,
                            f'Đã xuất phần có tồn cho {res.request.code}. '
                            f'Còn thiếu sẽ bổ sung khi có hàng (phiếu {res.stock_issue.number}).',
                        )
                    elif allow_partial:
                        messages.success(
                            request,
                            f'Đã bổ sung xuất đủ cho {res.request.code} '
                            f'(phiếu {res.stock_issue.number}).',
                        )
                    else:
                        messages.success(request, f'Yêu cầu xuất {res.request.code} đã duyệt.')
                    return redirect('san_xuat:dispatch_material_issue_req_detail', pk=res.request.pk)
            else:
                messages.error(request, 'Không duyệt được yêu cầu xuất — kiểm tra lại form.')

    else:
        form = MaterialIssueApproveForm()

    ycx_can_edit_loc = bool(
        can_update
        and req.status not in ('done', 'cancelled')
        and (
            not req.stock_issue_id
            or req.status == 'partial'
            or getattr(req.stock_issue, 'status', '') == 'draft'
        )
    )
    ycx_can_approve = bool(
        can_update
        and req.status in ('draft', 'submitted', 'approved', 'partial')
        and (
            not req.stock_issue_id
            or req.status == 'partial'
            or getattr(req.stock_issue, 'status', '') == 'draft'
        )
    )

    return render(request, 'san_xuat/dispatch_material_issue_req_detail.html', {
        **_perm_ctx(request),
        'req': req,
        'form': form,
        'can_update': can_update,
        'stock_issue': stock_issue,
        'ycx_can_edit_loc': ycx_can_edit_loc,
        'ycx_can_approve': ycx_can_approve,
        **_ycx_detail_context(req),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_prod_stats(request):
    """Tab mặc định: công đoạn của tôi; ?tab=stats = danh sách phiếu TKSX."""
    tab = (request.GET.get('tab') or 'mine').strip().lower()
    if tab not in ('mine', 'stats'):
        tab = 'mine'

    if tab == 'stats':
        base_qs = (
            SxProductionStat.objects.filter(is_demo=False)
            .order_by('-stat_date', '-pk')
            .select_related('production_order')
        )
        stats, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PROD_STAT, list_key='dispatch_prod_stat')
        return render(request, 'san_xuat/dispatch_prod_stats_list.html', {
            **_perm_ctx(request),
            'stats': stats,
            'tab': tab,
            **fctx,
        })

    user = request.user
    managed = (
        SxMoProcessStep.objects.filter(manager=user)
        .exclude(production_order__status=SxProductionOrder.STATUS_CANCELLED)
        .select_related('production_order', 'work_center', 'manager')
        .prefetch_related('assignees')
        .order_by('-production_order_id', 'sequence', 'id')
    )
    assigned = (
        SxMoProcessStep.objects.filter(assignees__user=user)
        .exclude(production_order__status=SxProductionOrder.STATUS_CANCELLED)
        .select_related('production_order', 'work_center', 'manager')
        .prefetch_related('assignees')
        .order_by('-production_order_id', 'sequence', 'id')
        .distinct()
    )
    # Gộp không trùng — ẩn việc tổ đã chốt (công nhân không chọn đơn đó làm tiếp)
    from san_xuat.hub_models import SxTeamWorkClose
    from san_xuat.services.progress_template import team_slug_for_process_label

    merged_steps = list(managed) + list(assigned)
    closed_pairs = set(
        SxTeamWorkClose.objects.filter(
            is_demo=False,
            production_order_id__in=[s.production_order_id for s in merged_steps],
        ).values_list('production_order_id', 'team_slug')
    )
    seen: set[int] = set()
    my_steps = []
    for step in merged_steps:
        if step.pk in seen:
            continue
        seen.add(step.pk)
        slug = team_slug_for_process_label(step.process_name or '')
        if slug and (step.production_order_id, slug) in closed_pairs:
            continue
        mo = step.production_order
        confirmed = SxProductionStat.objects.filter(
            production_order=mo,
            process_name__iexact=step.process_name,
            status=SxProductionStat.STATUS_CONFIRMED,
            is_demo=False,
        )
        qty_good = sum((s.qty_good or Decimal('0') for s in confirmed), Decimal('0'))
        my_steps.append({
            'step': step,
            'mo': mo,
            'assignee_count': step.assignees.count(),
            'qty_good': qty_good,
            'is_manager': step.manager_id == user.pk,
            'is_assignee': user_can_stat_mo_step(user=user, step=step),
        })

    return render(request, 'san_xuat/dispatch_mo_process_board.html', {
        **_perm_ctx(request),
        'tab': tab,
        'my_steps': my_steps,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo_process_step_detail(request, pk: int):
    step = get_object_or_404(
        SxMoProcessStep.objects.select_related(
            'production_order', 'work_center', 'manager', 'manager__profile',
        ).prefetch_related('assignees__user__profile'),
        pk=pk,
    )
    mo = step.production_order
    can_update = _perm_ctx(request).get('can_update')
    is_manager = user_can_manage_mo_step(user=request.user, step=step)
    is_assignee = user_can_stat_mo_step(user=request.user, step=step)
    can_set_manager = bool(can_update and (is_manager or not step.manager_id or request.user.is_superuser))

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'set_manager' and can_set_manager:
            raw = (request.POST.get('manager_id') or '').strip()
            mgr = None
            if raw.isdigit():
                from django.contrib.auth import get_user_model
                mgr = get_user_model().objects.filter(pk=int(raw), is_active=True).first()
            step.manager = mgr
            step.save(update_fields=['manager'])
            messages.success(request, 'Đã cập nhật quản lý công đoạn.')
            return redirect('san_xuat:dispatch_mo_process_step_detail', pk=step.pk)
        if action in ('assign', 'assign_self'):
            messages.info(
                request,
                'Phân công nhân viên ghi thống kê SX đã chuyển sang menu Công việc tổ.',
            )
            return redirect('san_xuat:dispatch_mo_process_step_detail', pk=step.pk)

    stats = (
        SxProductionStat.objects.filter(
            production_order=mo,
            process_name__iexact=step.process_name,
            is_demo=False,
        )
        .order_by('-stat_date', '-pk')[:30]
    )

    from san_xuat.forms_dispatch import mo_manager_candidate_options
    from san_xuat.services.progress_template import team_slug_for_process_label

    assignee_labels = []
    for a in step.assignees.all():
        u = a.user
        prof = getattr(u, 'profile', None)
        label = ((getattr(prof, 'full_name', None) or '') if prof else '').strip()
        label = label or u.get_full_name() or u.username
        assignee_labels.append(label)

    team_slug = team_slug_for_process_label(step.process_name)
    team_work_url = ''
    if team_slug:
        team_work_url = (
            f"{reverse('san_xuat:team_work_board', kwargs={'slug': team_slug})}"
            f"?q={mo.code}"
        )

    return render(request, 'san_xuat/dispatch_mo_process_step_detail.html', {
        **_perm_ctx(request),
        'step': step,
        'mo': mo,
        'stats': stats,
        'is_manager': is_manager,
        'is_assignee': is_assignee,
        'can_set_manager': can_set_manager,
        'manager_options': mo_manager_candidate_options() if can_set_manager else [],
        'assignee_labels': assignee_labels,
        'team_work_url': team_work_url,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_prod_stats_create(request):
    mo_id = request.GET.get('mo') or request.POST.get('production_order')
    step_id = request.GET.get('step') or request.POST.get('mo_process_step')
    mo = None
    mo_step = None
    if step_id:
        mo_step = get_object_or_404(
            SxMoProcessStep.objects.select_related('production_order', 'work_center'),
            pk=step_id,
        )
        mo = mo_step.production_order
    elif mo_id:
        mo = get_object_or_404(
            SxProductionOrder.objects.select_related('bom_version').prefetch_related('lines'),
            pk=mo_id,
        )

    if request.method == 'POST':
        mo = get_object_or_404(
            SxProductionOrder.objects.select_related('bom_version').prefetch_related('lines'),
            pk=request.POST.get('production_order'),
        )
        step_post = (request.POST.get('mo_process_step') or '').strip()
        if step_post.isdigit():
            mo_step = SxMoProcessStep.objects.filter(pk=int(step_post), production_order=mo).first()
        form = ProductionStatCreateForm(request.POST, mo=mo, mo_step=mo_step, user=request.user)
        if form.is_valid():
            try:
                if mo_step:
                    assert_user_can_create_stat(
                        user=request.user, mo=mo, process_name=mo_step.process_name,
                    )
                stat = create_production_stat(
                    production_order_id=mo.pk,
                    stat_date=form.cleaned_data['stat_date'],
                    process_name=form.cleaned_data.get('process_name') or '',
                    qty_good=form.cleaned_data.get('qty_good') or 0,
                    qty_defect=form.cleaned_data.get('qty_defect') or 0,
                    team_label=form.cleaned_data.get('team_label') or '',
                    size_label=form.cleaned_data.get('size_label') or '',
                    sku_code=form.cleaned_data.get('sku_code') or '',
                    color_label=form.cleaned_data.get('color_label') or '',
                    color_code=form.cleaned_data.get('color_code') or '',
                    notes=form.cleaned_data.get('notes') or '',
                    code=form.cleaned_data.get('code') or None,
                    user=request.user,
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã tạo thống kê SX {stat.code}.')
                return redirect('san_xuat:dispatch_prod_stats_detail', pk=stat.pk)
        else:
            messages.error(request, 'Không tạo được thống kê SX — kiểm tra lại form.')
    else:
        if mo_step and not user_can_stat_mo_step(user=request.user, step=mo_step):
            messages.error(request, 'Bạn chưa được phân ghi thống kê (Công việc tổ) cho công đoạn này.')
            return redirect('san_xuat:dispatch_mo_process_step_detail', pk=mo_step.pk)
        initial = production_stat_initial_from_mo(mo)
        if mo_step:
            initial['process_name'] = mo_step.process_name
            initial['team_label'] = mo_step.team_label or initial.get('team_label') or ''
        form = ProductionStatCreateForm(
            initial=initial,
            mo=mo,
            mo_step=mo_step,
            user=request.user,
        )
    mo_line_qty = []
    if mo:
        from san_xuat.services.dispatch import format_mo_line_qty

        for ln in mo.lines.all():
            mo_line_qty.append({
                'color': (ln.color_code or '').strip().upper(),
                'size': (ln.size_label or '').strip().upper(),
                'qty': format_mo_line_qty(ln.qty) or '0',
                'sku': (ln.sku_code or '').strip().upper(),
            })
    return render(request, 'san_xuat/dispatch_prod_stats_form.html', {
        **_perm_ctx(request),
        'form': form,
        'mo': mo,
        'mo_step': mo_step,
        'mo_line_qty_json': mo_line_qty,
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
                messages.success(request, f'Đã tạo yêu cầu kiểm tra {qc_req.code} từ thống kê SX.')
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
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_FG_RECEIPT, list_key='dispatch_fg_receipt')
    return render(request, 'san_xuat/dispatch_fg_receipt_req_list.html', {
        **_perm_ctx(request),
        'requests': requests_qs,
        **fctx,
    })


@module_perm_required(MODULE_SAN_XUAT, 'create')
def dispatch_fg_receipt_req_create(request):
    mo = None
    stat = None
    stat_id = (request.POST.get('stat_id') or request.GET.get('stat') or '').strip()
    if stat_id.isdigit():
        stat = get_object_or_404(SxProductionStat, pk=int(stat_id))
        mo = stat.production_order

    if request.method == 'POST':
        form = FgReceiptCreateForm(request.POST, extra_mo=mo, operator=request.user)
        line_formset = FgReceiptLineFormSet(request.POST, prefix='lines')
        if form.is_valid() and line_formset.is_valid():
            mo = form.cleaned_data['production_order']
            lines = []
            for lf in line_formset:
                cd = lf.cleaned_data
                if not cd or cd.get('DELETE'):
                    continue
                if cd.get('qty') and cd['qty'] > 0:
                    lines.append(cd)
            try:
                fg_req = create_fg_receipt_from_mo(
                    production_order_id=mo.pk,
                    stat_id=stat.pk if stat else None,
                    qty=form.cleaned_data.get('qty'),
                    notes=form.cleaned_data.get('notes') or '',
                    request_date=form.cleaned_data.get('request_date'),
                    lines=lines,
                    received_by=form.cleaned_data.get('received_by'),
                    warehouse_code=form.cleaned_data.get('warehouse_code') or '',
                    warehouse_name=form.cleaned_data.get('warehouse_name') or '',
                )
            except DispatchError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã lưu yêu cầu nhập thành phẩm {fg_req.code}.')
                return redirect('san_xuat:dispatch_fg_receipt_req_detail', pk=fg_req.pk)
        else:
            messages.error(request, 'Không tạo được yêu cầu nhập thành phẩm — kiểm tra lại form.')
            raw = request.POST.get('production_order')
            if raw and str(raw).isdigit():
                mo = SxProductionOrder.objects.filter(pk=int(raw)).first() or mo
    else:
        initial = {'request_date': timezone.localdate(), 'received_by': request.user}
        initial_lines = None
        mo_id = request.GET.get('mo')
        if not mo and mo_id and str(mo_id).isdigit():
            mo = get_object_or_404(SxProductionOrder, pk=int(mo_id))
        if mo:
            source = fg_receipt_prefill(mo=mo, stat=stat)
            initial['production_order'] = mo
            initial['product_code'] = source['product_code']
            initial['product_name'] = source['product_name']
            initial['qty'] = source['qty']
            initial_lines = source['lines'] or None
        form = FgReceiptCreateForm(initial=initial, extra_mo=mo, operator=request.user)
        line_formset = make_fg_receipt_line_formset(initial=initial_lines)
    return render(request, 'san_xuat/dispatch_fg_receipt_req_form.html', {
        **_perm_ctx(request),
        'form': form,
        'line_formset': line_formset,
        'mo': mo,
        'stat': stat,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_fg_receipt_req_detail(request, pk: int):
    fg_req = get_object_or_404(
        SxFgReceiptRequest.objects.select_related(
            'production_order', 'production_stat', 'received_by', 'received_by__profile',
        ).prefetch_related('lines'),
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
                messages.success(request, f'Yêu cầu nhập thành phẩm {fg_req.code} đã gửi.')
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
    items, fctx = prepare_hub_list(request, base_qs, SX_FILTER_NPL_SURPLUS, list_key='npl_surplus')
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
    handovers, fctx = prepare_hub_list(request, base_qs, SX_FILTER_WIP_HANDOVER, list_key='wip_handover')
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
    returns, fctx = prepare_hub_list(request, base_qs, SX_FILTER_WIP_RETURN, list_key='wip_return')
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
    from san_xuat.services.handover_status import build_handover_board

    q = (request.GET.get('q') or '').strip()
    team = (request.GET.get('team') or '').strip().lower()
    board = build_handover_board(search=q, team_slug=team)
    return render(request, 'san_xuat/wip_handover_status.html', {
        **_perm_ctx(request),
        'board': board,
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
    requests_qs, fctx = prepare_hub_list(request, base_qs, SX_FILTER_QC_REQUEST, list_key='qc_request')
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
                from san_xuat.services.sx_settings import sx_prefix
                qc_req.code = _next_code(sx_prefix('qc_req'), SxQcRequest)
            qc_req.is_demo = False
            qc_req.save()
            messages.success(request, f'Đã tạo yêu cầu kiểm tra {qc_req.code}.')
            return redirect('san_xuat:qc_request_detail', pk=qc_req.pk)
        messages.error(request, 'Không tạo được yêu cầu kiểm tra - kiểm tra lại form.')
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
    inspections, fctx = prepare_hub_list(request, base_qs, SX_FILTER_QC_SHEET, list_key='qc_sheet')
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
                messages.success(request, f'Đã tạo phiếu kiểm tra {inspection.code}.')
                return redirect('san_xuat:qc_sheet_detail', pk=inspection.pk)
        messages.error(request, 'Không tạo được phiếu kiểm tra - kiểm tra lại form.')
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
                    messages.success(request, f'Phiếu kiểm tra {inspection.code} đã chốt kết quả.')
                    return redirect('san_xuat:qc_sheet_detail', pk=inspection.pk)
            messages.error(request, 'Không chốt được phiếu kiểm tra - kiểm tra lại dữ liệu.')
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
    alerts, fctx = prepare_hub_list(request, base_qs, SX_FILTER_QC_ALERT, preserve=preserve, list_key='qc_alert')
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
        export_key='qc_criteria',
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
        export_key='qc_criteria_group',
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
        export_key='qc_sampling',
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
        export_key='qc_standard_set',
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
        export_key='qc_defect',
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
        export_key='qc_defect_group',
    )


def _qc_catalog_list(request, *, title, subtitle, model, fields, labels, create_url_name, export_key=''):
    filters = parse_sx_list_filters(request)
    qs = apply_sx_list_filters(
        model.objects.filter(is_demo=False).order_by('code'),
        filters,
        SX_FILTER_QC_CATALOG,
    )[:200]
    return render(request, 'san_xuat/qc_catalog_list.html', {
        **_perm_ctx(request),
        'hub_title': title,
        'hub_subtitle': subtitle,
        'columns': labels,
        'rows': _rows_from_queryset(qs, fields),
        'create_url_name': create_url_name,
        'export_key': export_key,
        **sx_filter_context(filters),
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
    """Đã thay bằng Công việc tổ — giữ URL cũ để bookmark không 404."""
    messages.info(request, 'Giao việc SX đã chuyển sang Công việc tổ (phân công theo bộ phận).')
    return redirect('san_xuat:team_work_hub')


def _can_team_work_overview(user) -> bool:
    from san_xuat.services.progress_template import TEAM_SLUGS

    if user_can_access_menu(user, MODULE_SAN_XUAT, 'team_work_goods'):
        return True
    if user_can_access_menu(user, MODULE_SAN_XUAT, 'team_work'):
        return True
    return any(
        user_can_access_menu(user, MODULE_SAN_XUAT, menu_key)
        for _slug, _gk, menu_key, _label in TEAM_SLUGS
    )


def _nav_team_for_user(user):
    """Tổ dùng cho nav Công việc / Quản lý nhân sự trên trang tổng (tiến độ hàng hoá)."""
    from san_xuat.services.progress_template import TEAM_SLUGS, team_by_slug

    for slug, _gk, menu_key, _label in TEAM_SLUGS:
        if user_can_access_menu(user, MODULE_SAN_XUAT, menu_key):
            return team_by_slug(slug)
    if user_can_access_menu(user, MODULE_SAN_XUAT, 'team_work'):
        return team_by_slug(TEAM_SLUGS[0][0])
    return team_by_slug('cat')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def team_work_hub(request):
    """Hub Công việc tổ → tiến độ hàng hoá, không thì tổ đầu tiên user có quyền."""
    from san_xuat.services.progress_template import TEAM_SLUGS

    if _can_team_work_overview(request.user):
        return redirect('san_xuat:team_work_goods')
    for slug, _gk, menu_key, _label in TEAM_SLUGS:
        if user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key):
            return redirect('san_xuat:team_work_board', slug=slug)
    return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'team_work')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def team_work_goods(request):
    """Tiến độ hàng hoá — mọi lệnh, công đoạn các tổ, đơn gấp để tổ trưởng xếp việc."""
    from PortalJustPlay.pagination import LIST_PAGE_SIZE, paginate_queryset
    from san_xuat.services.goods_progress import build_goods_progress_board

    if not _can_team_work_overview(request.user):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'team_work_goods')

    board = build_goods_progress_board(
        search=(request.GET.get('q') or '').strip(),
        priority=(request.GET.get('priority') or '').strip(),
        mo_status=(request.GET.get('status') or '').strip(),
        due=(request.GET.get('due') or '').strip(),
        sort=(request.GET.get('sort') or '').strip(),
    )
    page_obj, query_string = paginate_queryset(request, board.rows, per_page=LIST_PAGE_SIZE)
    return render(request, 'san_xuat/team_work_goods.html', {
        **_perm_ctx(request),
        'board': board,
        'page_obj': page_obj,
        'query_string': query_string,
        'team': _nav_team_for_user(request.user),
        'tw_section': 'goods',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def team_work_board(request, slug: str):
    """Bảng công việc theo tổ — phân công CD con cho NV."""
    from san_xuat.services.planning import PlanningError
    from san_xuat.services.progress_template import team_by_slug
    from san_xuat.services.team_work import (
        assignee_candidate_options,
        assign_team_work,
        attach_team_job_closes,
        build_team_work_rows,
        close_team_job,
        group_team_work_jobs,
        reopen_team_job,
    )

    team_meta = team_by_slug(slug)
    if not team_meta:
        messages.error(request, 'Tổ không hợp lệ.')
        return redirect('san_xuat:team_work_hub')

    menu_key = team_meta['menu_key']
    if not (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'team_work')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, menu_key)

    can_assign = (
        user_can_update_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'team_work')
        or user_can_create_menu(request.user, MODULE_SAN_XUAT, menu_key)
    )

    def _board_qs(**extra) -> str:
        from urllib.parse import urlencode

        params = {}
        qv = (request.GET.get('q') or request.POST.get('q') or '').strip()
        show = (request.GET.get('show') or request.POST.get('show') or '').strip()
        if qv:
            params['q'] = qv
        if show == 'closed':
            params['show'] = 'closed'
        params.update({k: v for k, v in extra.items() if v})
        qs = urlencode(params)
        url = reverse('san_xuat:team_work_board', kwargs={'slug': slug})
        return f'{url}?{qs}' if qs else url

    if request.method == 'POST' and can_assign:
        action = (request.POST.get('action') or '').strip()
        try:
            mo_id = int(request.POST.get('mo_id') or 0)
        except (TypeError, ValueError):
            mo_id = 0
        if action == 'assign':
            process_key = (request.POST.get('process_key') or '').strip()
            raw_ids = request.POST.getlist('assignee_ids')
            user_ids = [int(x) for x in raw_ids if str(x).isdigit()]
            try:
                assign_team_work(
                    mo_id=mo_id,
                    process_key=process_key,
                    user_ids=user_ids,
                    assigned_by=request.user,
                    team_slug=slug,
                )
                messages.success(request, 'Đã cập nhật phân công.')
            except PlanningError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect(_board_qs())
        if action == 'complete' and mo_id:
            try:
                close_team_job(mo_id=mo_id, team_slug=slug, user=request.user)
                messages.success(
                    request,
                    'Đã hoàn thành — công nhân tổ này không chọn đơn đó làm tiếp. Tổ sau không bị chặn.',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect(_board_qs())
        if action == 'reopen' and mo_id:
            try:
                reopen_team_job(mo_id=mo_id, team_slug=slug)
                messages.success(request, 'Đã mở lại công việc tổ trên lệnh này.')
            except PlanningError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect(_board_qs())

    q = (request.GET.get('q') or '').strip()
    show_closed = (request.GET.get('show') or '').strip() == 'closed'
    try:
        team, rows = build_team_work_rows(slug=slug, search=q)
    except PlanningError as exc:
        messages.error(request, str(exc))
        return redirect('san_xuat:team_work_hub')

    from san_xuat.services.team_division_map import has_mapped_divisions

    can_map = user_can_update_menu(request.user, MODULE_SAN_XUAT, 'general_settings')
    mapped = has_mapped_divisions(slug)

    assignee_candidates = []
    if can_assign:
        assignee_candidates = assignee_candidate_options(slug=slug, assigner=request.user)
        # Giữ option cho NV đã gán (có thể ngoài pool sau khi đổi map) để không mất khi mở modal.
        seen = {c['id'] for c in assignee_candidates}
        for row in rows:
            for a in row.assignees:
                if a['id'] not in seen:
                    assignee_candidates.append({'id': a['id'], 'label': a['label']})
                    seen.add(a['id'])

    jobs = attach_team_job_closes(group_team_work_jobs(rows), slug=slug)
    closed_count = sum(1 for j in jobs if j.closed)
    open_count = len(jobs) - closed_count
    visible = [j for j in jobs if j.closed] if show_closed else [j for j in jobs if not j.closed]

    return render(request, 'san_xuat/team_work_board.html', {
        **_perm_ctx(request),
        'team': team,
        'jobs': visible,
        'search_query': q,
        'show_closed': show_closed,
        'open_count': open_count,
        'closed_count': closed_count,
        'can_assign': can_assign,
        'can_map_divisions': can_map,
        'team_has_division_map': mapped,
        'assignee_candidates': assignee_candidates,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def team_work_personnel(request, slug: str):
    """Danh sách nhân sự tổ — hồ sơ năng lực, việc đang gán, hiệu suất gần đây."""
    from san_xuat.services.planning import PlanningError
    from san_xuat.services.progress_template import team_by_slug
    from san_xuat.services.team_personnel import (
        build_team_personnel_board,
        can_edit_team_personnel,
        upsert_team_personnel_skill,
    )

    team_meta = team_by_slug(slug)
    if not team_meta:
        messages.error(request, 'Tổ không hợp lệ.')
        return redirect('san_xuat:team_work_hub')

    menu_key = team_meta['menu_key']
    if not (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'team_work')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, menu_key)

    can_edit = can_edit_team_personnel(request.user, slug)

    def _list_url(**extra) -> str:
        from urllib.parse import urlencode

        params = {}
        qv = (request.GET.get('q') or request.POST.get('q') or '').strip()
        if qv:
            params['q'] = qv
        params.update({k: v for k, v in extra.items() if v})
        qs = urlencode(params)
        url = reverse('san_xuat:team_work_personnel', kwargs={'slug': slug})
        return f'{url}?{qs}' if qs else url

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'Bạn không có quyền cập nhật hồ sơ năng lực tổ này.')
            return redirect(_list_url())
        try:
            user_id = int(request.POST.get('user_id') or 0)
        except (TypeError, ValueError):
            user_id = 0
        try:
            from san_xuat.services.progress_template import steps_for_group
            from san_xuat.services.team_personnel import parse_process_avg_qty_post

            allowed_process_keys = {
                s.key for s in steps_for_group(team_meta['group_key'])
            }
            upsert_team_personnel_skill(
                slug=slug,
                user_id=user_id,
                process_keys=request.POST.getlist('process_keys'),
                process_avg_qty=parse_process_avg_qty_post(
                    request.POST,
                    allowed=allowed_process_keys,
                ),
                skill_level=(request.POST.get('skill_level') or '').strip(),
                machines=(request.POST.getlist('machine_codes') or None) or (request.POST.get('machines') or '').strip(),
                is_multiskill=(request.POST.get('is_multiskill') or '').strip() in (
                    '1', 'on', 'true', 'yes',
                ),
                notes=(request.POST.get('notes') or '').strip(),
                updated_by=request.user,
            )
            messages.success(request, 'Đã cập nhật hồ sơ năng lực.')
        except PlanningError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect(_list_url())

    q = (request.GET.get('q') or '').strip()
    try:
        board = build_team_personnel_board(slug=slug, search=q)
    except PlanningError as exc:
        messages.error(request, str(exc))
        return redirect('san_xuat:team_work_hub')

    from san_xuat.services.production_machines import machine_options_for_codes
    from san_xuat.services.team_division_map import has_mapped_divisions

    can_map = user_can_update_menu(request.user, MODULE_SAN_XUAT, 'general_settings')
    edit_payload = {
        str(row.user_id): {
            'user_id': row.user_id,
            'full_name': row.full_name,
            'process_keys': row.skill.process_keys,
            'process_avg_qty': row.skill.process_avg_qty,
            'skill_level': row.skill.skill_level,
            'machine_codes': row.skill.machine_codes,
            'machine_options': machine_options_for_codes(row.skill.machine_codes),
            'is_multiskill': row.skill.is_multiskill,
            'notes': row.skill.notes,
        }
        for row in board.rows
    }

    return render(request, 'san_xuat/team_work_personnel.html', {
        **_perm_ctx(request),
        'team': board.team,
        'board': board,
        'search_query': q,
        'can_edit': can_edit,
        'can_map_divisions': can_map,
        'team_has_division_map': has_mapped_divisions(slug),
        'edit_payload': edit_payload,
        'skill_choices': (
            ('', 'Chưa xếp'),
            ('A', 'A'),
            ('B', 'B'),
            ('C', 'C'),
        ),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def team_work_progress(request, slug: str, mo_id: int):
    """Phiếu tiến độ theo tổ — xem/ghi SL công đoạn của tổ, không cần vào KHSX."""
    from decimal import Decimal, InvalidOperation

    from san_xuat.hub_models import SxProductionOrder
    from san_xuat.services.order_progress_sheet import (
        build_progress_sheet,
        ensure_progress_work_centers,
        set_progress_done_qty,
    )
    from san_xuat.services.planning import PlanningError
    from san_xuat.services.progress_template import steps_for_group, team_by_slug
    from san_xuat.services.team_work import close_team_job, is_team_job_closed, reopen_team_job

    team_meta = team_by_slug(slug)
    if not team_meta:
        messages.error(request, 'Tổ không hợp lệ.')
        return redirect('san_xuat:team_work_hub')

    menu_key = team_meta['menu_key']
    if not (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_access_menu(request.user, MODULE_SAN_XUAT, 'team_work')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, menu_key)

    can_update = (
        user_can_update_menu(request.user, MODULE_SAN_XUAT, menu_key)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, 'team_work')
        or user_can_create_menu(request.user, MODULE_SAN_XUAT, menu_key)
    )

    mo = (
        SxProductionOrder.objects.filter(pk=mo_id, is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .exclude(status=SxProductionOrder.STATUS_DRAFT)
        .select_related('sales_order')
        .first()
    )
    if not mo:
        messages.error(request, 'Không tìm thấy lệnh sản xuất đang chạy.')
        return redirect('san_xuat:team_work_board', slug=slug)

    group_key = team_meta['group_key']
    team_steps = steps_for_group(group_key)
    allowed_keys = {s.key for s in team_steps}
    ensure_progress_work_centers()
    job_closed = is_team_job_closed(mo_id=mo.pk, team_slug=slug)

    if request.method == 'POST' and can_update:
        from django.http import JsonResponse

        action = (request.POST.get('action') or '').strip()
        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in (request.headers.get('Accept') or '')
        )
        if action == 'complete':
            try:
                close_team_job(mo_id=mo.pk, team_slug=slug, user=request.user)
                messages.success(
                    request,
                    'Đã hoàn thành — công nhân tổ này không chọn đơn đó làm tiếp. Tổ sau không bị chặn.',
                )
            except PlanningError as exc:
                messages.error(request, str(exc))
            return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)
        if action == 'reopen':
            try:
                reopen_team_job(mo_id=mo.pk, team_slug=slug)
                messages.success(request, 'Đã mở lại công việc tổ trên lệnh này.')
            except PlanningError as exc:
                messages.error(request, str(exc))
            return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)
        if action in ('record', 'set_done'):
            if job_closed:
                msg = 'Tổ đã hoàn thành lệnh này — mở lại nếu cần sửa SL.'
                if wants_json:
                    return JsonResponse({'ok': False, 'error': msg}, status=400)
                messages.error(request, msg)
                return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)
            process_key = (request.POST.get('process_key') or '').strip()
            size_label = (request.POST.get('size_label') or '').strip()
            try:
                qty = Decimal(str(request.POST.get('qty') or '0').replace(',', '').strip() or '0')
            except (InvalidOperation, ValueError):
                qty = Decimal('0')
            if process_key not in allowed_keys:
                msg = 'Công đoạn không thuộc tổ này.'
                if wants_json:
                    return JsonResponse({'ok': False, 'error': msg}, status=400)
                messages.error(request, msg)
                return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)
            try:
                result = set_progress_done_qty(
                    mo_id=mo.pk,
                    process_key=process_key,
                    size_label=size_label,
                    qty=qty,
                    user=request.user,
                )
            except PlanningError as exc:
                if wants_json:
                    return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
                messages.error(request, str(exc))
                return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)
            except Exception as exc:
                if wants_json:
                    return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
                messages.error(request, str(exc))
                return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)
            if wants_json:
                plan_qty = Decimal('0')
                for row in build_progress_sheet(mo, group_key=group_key).done_rows:
                    if row['size_label'] == size_label or (
                        size_label == 'Tổng' and row['size_label'] == 'Tổng'
                    ):
                        plan_qty = Decimal(str(row['qty'] or 0))
                        break
                done = Decimal(str(result['done'] or 0))
                remain = plan_qty - done
                if remain < 0:
                    remain = Decimal('0')
                return JsonResponse({
                    'ok': True,
                    'changed': result['changed'],
                    'done': str(done),
                    'remain': str(remain),
                })
            if result['changed']:
                messages.success(request, 'Đã cập nhật SL thực hiện.')
            return redirect('san_xuat:team_work_progress', slug=slug, mo_id=mo.pk)

    sheet = build_progress_sheet(mo, group_key=group_key)

    return render(request, 'san_xuat/team_work_progress.html', {
        **_perm_ctx(request),
        'team': team_meta,
        'mo': mo,
        'sheet': sheet,
        'flat_steps': team_steps,
        'can_update': can_update and not job_closed,
        'can_close': can_update,
        'job_closed': job_closed,
        'today': timezone.localdate(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def team_division_map(request):
    """Bookmark cũ → Thiết lập chung · Map bộ phận."""
    return redirect(f"{reverse('san_xuat:general_settings')}#sec-team-map")


@module_perm_required(MODULE_SAN_XUAT, 'view')
def work_assignment_create(request):
    """Đã thay bằng Công việc tổ — giữ URL cũ để bookmark không 404."""
    messages.info(request, 'Giao việc SX đã chuyển sang Công việc tổ (phân công theo bộ phận).')
    return redirect('san_xuat:team_work_hub')


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
    """Thiết lập chung sản xuất — cổng quy trình, ngưỡng truy xuất, danh mục SKU."""
    from san_xuat.forms_settings import SxGeneralSettingsForm
    from san_xuat.hub_models import SxColor, SxGeneralSettings, SxSize
    from san_xuat.services.sku_catalog import (
        SkuError,
        ensure_color,
        ensure_size,
        update_color,
        update_size,
    )

    cfg = SxGeneralSettings.load()
    can_update = _perm_ctx(request).get('can_update')

    if request.method == 'POST':
        if not can_update:
            messages.error(request, 'Bạn không có quyền cập nhật thiết lập.')
            return redirect('san_xuat:general_settings')

        action = (request.POST.get('action') or 'save_settings').strip()
        redirect_sku = redirect(f"{reverse('san_xuat:general_settings')}#sec-sku")

        if action == 'add_color':
            try:
                color = ensure_color(
                    code=request.POST.get('color_code') or '',
                    name=request.POST.get('color_name') or '',
                    user=request.user,
                )
            except SkuError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã thêm / kích hoạt màu {color.code}.')
            return redirect_sku

        if action == 'save_color':
            try:
                color = update_color(
                    color_id=int(request.POST.get('color_id') or 0),
                    name=request.POST.get('color_name'),
                    sort_order=request.POST.get('color_sort_order'),
                    is_active=(request.POST.get('color_is_active') == '1'),
                )
            except (SkuError, TypeError, ValueError) as exc:
                messages.error(request, str(exc) if isinstance(exc, SkuError) else 'Màu không hợp lệ.')
            else:
                messages.success(request, f'Đã cập nhật màu {color.code}.')
            return redirect_sku

        if action == 'add_size':
            try:
                size = ensure_size(
                    code=request.POST.get('size_code') or '',
                    name=request.POST.get('size_name') or '',
                    user=request.user,
                )
            except SkuError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'Đã thêm / kích hoạt size {size.code}.')
            return redirect_sku

        if action == 'save_size':
            try:
                size = update_size(
                    size_id=int(request.POST.get('size_id') or 0),
                    name=request.POST.get('size_name'),
                    sort_order=request.POST.get('size_sort_order'),
                    is_active=(request.POST.get('size_is_active') == '1'),
                )
            except (SkuError, TypeError, ValueError) as exc:
                messages.error(request, str(exc) if isinstance(exc, SkuError) else 'Size không hợp lệ.')
            else:
                messages.success(request, f'Đã cập nhật size {size.code}.')
            return redirect_sku

        if action in ('add_ie_approver', 'remove_ie_approver'):
            from san_xuat.ie_permissions import (
                IE_APPROVER_GROUP,
                add_ie_approver_by_username,
                remove_ie_approver_by_username,
            )

            redirect_ie = redirect('san_xuat:ie_approver_manage')
            username = (request.POST.get('username') or '').strip()
            try:
                if action == 'add_ie_approver':
                    user, created = add_ie_approver_by_username(username)
                    if created:
                        messages.success(request, f'Đã thêm {user.username} vào nhóm {IE_APPROVER_GROUP}.')
                    else:
                        messages.info(request, f'{user.username} đã là người duyệt.')
                else:
                    user = remove_ie_approver_by_username(username)
                    messages.success(request, f'Đã gỡ {user.username} khỏi nhóm {IE_APPROVER_GROUP}.')
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(f"{reverse('san_xuat:general_settings')}#sec-ie-approver")
            return redirect_ie

        if action in ('save_team_map', 'suggest_team_map'):
            from san_xuat.services.team_division_map import (
                save_team_maps,
                suggest_maps_from_names,
                team_slug_choices,
            )

            redirect_map = redirect(f"{reverse('san_xuat:general_settings')}#sec-team-map")
            if action == 'suggest_team_map':
                request.session['sx_team_map_preview'] = suggest_maps_from_names()
                messages.info(
                    request,
                    'Đã điền gợi ý theo tên bộ phận — kiểm tra rồi bấm Lưu map để áp dụng.',
                )
                return redirect_map
            payload: dict[str, list[int]] = {}
            for slug, _label in team_slug_choices():
                raw = request.POST.getlist(f'divisions_{slug}')
                payload[slug] = [int(x) for x in raw if str(x).isdigit()]
            stats = save_team_maps(payload, saved_by=request.user)
            request.session.pop('sx_team_map_preview', None)
            messages.success(
                request,
                f"Đã lưu map bộ phận → tổ: thêm {stats['created']}, "
                f"cập nhật {stats['updated']}, tắt {stats['deactivated']}.",
            )
            return redirect_map

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

    colors = list(SxColor.objects.order_by('sort_order', 'code'))
    sizes = list(SxSize.objects.order_by('sort_order', 'code'))

    from django.contrib.auth import get_user_model
    from san_xuat.ie_permissions import (
        IE_APPROVER_GROUP,
        ensure_ie_approver_group,
        ie_approver_group_has_members,
    )

    ie_group = ensure_ie_approver_group()
    ie_approvers = list(ie_group.user_set.order_by('username'))
    User = get_user_model()
    ie_candidate_users = list(User.objects.filter(is_active=True).order_by('username')[:300])

    from san_xuat.services.team_division_map import (
        current_maps_by_slug,
        sx_production_divisions,
        team_slug_choices,
    )

    team_map_selected = request.session.pop('sx_team_map_preview', None) or current_maps_by_slug()
    team_map_teams = [
        {
            'slug': slug,
            'label': label,
            'selected_ids': set(team_map_selected.get(slug) or []),
        }
        for slug, label in team_slug_choices()
    ]
    team_map_divisions = list(sx_production_divisions().select_related('department'))

    return render(request, 'san_xuat/general_settings.html', {
        **_perm_ctx(request),
        'form': form,
        'cfg': cfg,
        'can_update': can_update,
        'sku_colors': colors,
        'sku_sizes': sizes,
        'ie_approver_group_name': IE_APPROVER_GROUP,
        'ie_approver_ready': ie_approver_group_has_members(),
        'ie_approvers': ie_approvers,
        'ie_candidate_users': ie_candidate_users,
        'team_map_teams': team_map_teams,
        'team_map_divisions': team_map_divisions,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def capacity_list(request):
    from san_xuat.list_filters import resolve_sx_period
    from san_xuat.services.phase3 import build_capacity_load

    can_update = _perm_ctx(request).get('can_update')
    if request.method == 'POST' and (request.POST.get('action') or '').strip() == 'sync_from_hrm':
        if not can_update:
            messages.error(request, 'Bạn không có quyền đồng bộ năng lực.')
            return redirect('san_xuat:capacity_list')
        from san_xuat.services.capacity_from_hrm import (
            remap_all_to_hr,
            sync_capacity_from_hrm,
        )

        result = sync_capacity_from_hrm()
        if not result.department:
            messages.error(request, 'Không tìm thấy phòng ban SẢN XUẤT trên HR.')
        else:
            remapped = remap_all_to_hr()
            messages.success(
                request,
                f'Đã đồng bộ từ HR ({result.department}): '
                f'+{result.created} · cập nhật {result.updated} · tắt {result.deactivated} · '
                f'remap BOM {remapped["process_steps"]} · nhóm IE {remapped["groups"]} · '
                f'dòng routing {remapped["routing_lines"]}.',
            )
        return redirect('san_xuat:capacity_list')

    month = (request.GET.get('month') or '').strip()
    date_from, date_to, filters = resolve_sx_period(request)

    from san_xuat.services.order_progress_sheet import ensure_progress_work_centers
    from san_xuat.services.progress_template import standard_work_center_codes

    ensure_progress_work_centers()
    seed_codes = list(standard_work_center_codes())
    # Thứ tự theo mẫu: Cắt → In-Ép → Thêu → May → Ủi-Gấp → GH
    from san_xuat.services.progress_template import WC_SEED

    seed_order = {code: i for i, (code, _n, _t) in enumerate(WC_SEED)}
    base_centers = (
        SxWorkCenter.objects.filter(
            is_demo=False,
            code__in=seed_codes,
        )
        .select_related('created_by')
    )
    from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context

    centers = apply_sx_list_sort(
        apply_sx_list_filters(base_centers, filters, SX_FILTER_WORK_CENTER),
        request,
        'capacity_catalog',
    )
    # Không sort tay → giữ thứ tự mẫu
    if not (request.GET.get('sort') or '').strip():
        centers = sorted(
            list(centers),
            key=lambda wc: seed_order.get(wc.code, 999),
        )
    load_rows = build_capacity_load(date_from=date_from, date_to=date_to)
    preserve = {'month': month} if month else None
    from san_xuat.services.sx_settings import sx_int

    from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context

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
        **sx_list_grid_context(request, 'capacity_catalog'),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def capacity_load_matrix(request):
    """Bookmark cũ /tai-theo-to/ → gộp vào Năng lực SX."""
    return redirect('san_xuat:capacity_list')


@module_perm_required(MODULE_SAN_XUAT, 'update')
def capacity_setup(request):
    """Chỉnh nhanh các tham số năng lực của toàn bộ tổ/chuyền đang dùng."""
    from django import forms
    from django.forms import modelformset_factory

    class CompactNumberInput(forms.NumberInput):
        """Hiển thị số không ép đuôi .00."""

        def format_value(self, value):
            if value is None or value == '':
                return None
            try:
                text = format(Decimal(str(value)), 'f')
            except Exception:
                return super().format_value(value)
            if '.' in text:
                text = text.rstrip('0').rstrip('.')
            return text or '0'

    class CapacitySetupForm(forms.ModelForm):
        class Meta:
            model = SxWorkCenter
            fields = ('capacity_per_day', 'shift_minutes_per_head', 'efficiency_pct')
            widgets = {
                'capacity_per_day': CompactNumberInput(
                    attrs={'class': 'form-control form-control-sm text-end', 'min': '0', 'step': 'any'},
                ),
                'shift_minutes_per_head': forms.NumberInput(
                    attrs={'class': 'form-control form-control-sm text-end', 'min': '0', 'max': '1440'},
                ),
                'efficiency_pct': CompactNumberInput(
                    attrs={'class': 'form-control form-control-sm text-end', 'min': '0', 'max': '200', 'step': 'any'},
                ),
            }
            labels = {
                'efficiency_pct': 'Tải (%)',
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['efficiency_pct'].label = 'Tải (%)'
            self.fields['efficiency_pct'].help_text = (
                '80 = thiếu người; 100 = bình thường; 150 = tăng ca.'
            )
            self.fields['efficiency_pct'].max_value = Decimal('200')
            self.fields['efficiency_pct'].min_value = Decimal('0')

        def clean_efficiency_pct(self):
            value = self.cleaned_data.get('efficiency_pct')
            if value is None:
                return Decimal('100')
            if value < 0 or value > 200:
                raise forms.ValidationError('Tải phải trong khoảng 0–200%.')
            return value

    # Nhân sự chỉ lấy từ HR (Đồng bộ HR) — không cho sửa tay trên màn này.
    CapacityFormSet = modelformset_factory(SxWorkCenter, form=CapacitySetupForm, extra=0)
    from django.db.models import Case, IntegerField, Value, When

    from san_xuat.services.order_progress_sheet import ensure_progress_work_centers
    from san_xuat.services.progress_template import WC_SEED, standard_work_center_codes

    ensure_progress_work_centers()
    order_whens = [When(code=code, then=Value(i)) for i, (code, _n, _t) in enumerate(WC_SEED)]
    centers = (
        SxWorkCenter.objects.filter(
            is_demo=False,
            is_active=True,
            code__in=standard_work_center_codes(),
        )
        .annotate(_seed_ord=Case(*order_whens, default=Value(999), output_field=IntegerField()))
        .order_by('_seed_ord', 'code')
    )
    formset = CapacityFormSet(request.POST or None, queryset=centers)
    if request.method == 'POST':
        if formset.is_valid():
            changed = len(formset.save())
            messages.success(request, f'Đã cập nhật năng lực cho {changed} tổ/chuyền.')
            return redirect('san_xuat:capacity_list')
        messages.error(request, 'Không lưu được thiết lập — kiểm tra lại các giá trị.')

    return render(request, 'san_xuat/capacity_setup.html', {
        **_perm_ctx(request),
        'formset': formset,
    })


def _parse_iso_date_safe(raw: str):
    from datetime import datetime

    text = (raw or '').strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        return None


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_audit_log(request):
    """Nhật ký thao tác kế hoạch — ai đổi kế hoạch, đổi lúc nào (P4)."""
    from san_xuat.hub_models import SxPlanAuditLog
    from san_xuat.services.plan_audit import OBJECT_LABELS, plan_audit_qs

    object_type = (request.GET.get('object_type') or '').strip()
    action = (request.GET.get('action') or '').strip()
    search = (request.GET.get('q') or '').strip()
    date_from = _parse_iso_date_safe(request.GET.get('from'))
    date_to = _parse_iso_date_safe(request.GET.get('to'))

    qs = plan_audit_qs(object_type=object_type, action=action, search=search)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    logs = list(qs[:300])
    return render(request, 'san_xuat/plan_audit_log.html', {
        **_perm_ctx(request),
        'logs': logs,
        'object_type': object_type,
        'action_value': action,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'object_choices': sorted(OBJECT_LABELS.items(), key=lambda kv: kv[1]),
        'action_choices': SxPlanAuditLog.ACTION_CHOICES,
        'truncated': len(logs) >= 300,
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
                    headcount=form.cleaned_data.get('headcount'),
                    shift_minutes_per_head=form.cleaned_data.get('shift_minutes_per_head'),
                    efficiency_pct=form.cleaned_data.get('efficiency_pct'),
                )
            except Phase3Error as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f'Đã thêm {center.code} — quỹ {center.available_minutes_per_day} phút/ngày.',
                )
                return redirect('san_xuat:capacity_list')
        messages.error(request, 'Không lưu được tổ/chuyền.')
    else:
        form = WorkCenterForm(initial={
            'is_active': True,
            'uom_label': 'SP',
            'shift_minutes_per_head': 480,
            'efficiency_pct': Decimal('100'),
        })
    return render(request, 'san_xuat/phase3_form.html', {
        **_perm_ctx(request),
        'form': form,
        'title': 'Thêm năng lực SX',
        'back_url': 'san_xuat:capacity_list',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ops_report(request):
    from san_xuat.list_filters import resolve_sx_period
    from san_xuat.services.phase3 import build_ops_report, export_ops_report_csv

    date_from, date_to, filters = resolve_sx_period(request)
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
        from hrm.module_permissions import user_can_export_module
        if not user_can_export_module(request.user, MODULE_SAN_XUAT):
            messages.error(request, 'Bạn không có quyền xuất Excel/CSV.')
            return redirect('san_xuat:ops_report')
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
        **sx_filter_context(filters),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def packing_list(request):
    base_qs = (
        SxPackingRecord.objects.filter(is_demo=False)
        .select_related('production_order', 'fg_receipt')
        .order_by('-pack_date', '-pk')
    )
    items, fctx = prepare_hub_list(request, base_qs, SX_FILTER_PACKING, list_key='packing')
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
                    user=request.user,
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
        'style_code': '',
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
    items, fctx = prepare_hub_list(request, base_qs, SX_FILTER_SUBCONTRACT, list_key='subcontract')
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
                if not cd or cd.get('DELETE'):
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
        messages.error(request, 'Không tạo được lệnh gia công.')
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
    from san_xuat.list_filters import resolve_sx_period
    from san_xuat.services.phase3 import compute_piece_rate_pay

    date_from, date_to, filters = resolve_sx_period(request)
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
        **sx_filter_context(filters),
    })
