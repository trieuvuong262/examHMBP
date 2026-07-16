"""Hub Sản xuất — overview, danh sách demo, deep-link redirects."""

from __future__ import annotations

from django.shortcuts import redirect, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT

from san_xuat.hub_list import _rows_from_queryset, hub_list_page
from san_xuat.hub_models import (
    SxDetailPlan,
    SxDisassemblyOrder,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxMaterialPlan,
    SxNplPurchaseRequest,
    SxNplSurplus,
    SxOrderPlanCost,
    SxOverallPlan,
    SxProductionOrder,
    SxProductionStat,
    SxPurchaseOrder,
    SxQcCriteria,
    SxQcCriteriaGroup,
    SxQcDefect,
    SxQcDefectGroup,
    SxQcInspection,
    SxQcRequest,
    SxQcSamplingMethod,
    SxQcStandardSet,
    SxStandardCostSheet,
    SxWipHandover,
    SxWipReturn,
)
from san_xuat.models import ProcessStep, ProductTechDoc
from san_xuat.views import _perm_ctx

_DEMO_HINT = 'Chưa có dữ liệu demo. Chạy: python manage.py seed_san_xuat_demo'


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
    doc_total = ProductTechDoc.objects.count()
    doc_active = ProductTechDoc.objects.filter(is_active=True).count()
    return render(request, 'san_xuat/hub_overview.html', {
        **_perm_ctx(request),
        'doc_total': doc_total,
        'doc_active': doc_active,
        'plan_count': SxOverallPlan.objects.filter(is_demo=True).count(),
        'mo_count': SxProductionOrder.objects.filter(is_demo=True).count(),
        'qc_count': SxQcInspection.objects.filter(is_demo=True).count(),
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
def costing_norm(request):
    return _page(
        request,
        title='Giá thành định mức sản phẩm',
        subtitle='Bảng chốt giá thành định mức theo kỳ (demo).',
        model=SxStandardCostSheet,
        fields=['code', 'name', 'date_from', 'date_to', '_status'],
        labels=['Mã', 'Tên bảng', 'Từ', 'Đến', 'Trạng thái'],
        related_url_name='san_xuat:doc_list',
        order_by='-date_from',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_by_order(request):
    return _page(
        request,
        title='Giá thành kế hoạch theo đơn đặt hàng',
        subtitle='Costing kế hoạch = định mức × SL đơn (demo).',
        model=SxOrderPlanCost,
        fields=['code', 'name', 'kv_order_code', 'total_cost', '_status'],
        labels=['Mã', 'Tên bảng', 'Đơn KV', 'Tổng GT', 'Trạng thái'],
        related_url_name='san_xuat:redirect_orders',
        order_by='-date_from',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_stub(request):
    return render(request, 'san_xuat/hub_plan.html', {**_perm_ctx(request)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall(request):
    return _page(
        request,
        title='Kế hoạch tổng thể',
        subtitle='KHTT — khối lượng SX theo kỳ (demo).',
        model=SxOverallPlan,
        fields=['code', 'name', 'date_from', 'date_to', '_status'],
        labels=['Mã', 'Tên', 'Từ', 'Đến', 'Trạng thái'],
        related_url_name='san_xuat:redirect_orders',
        order_by='-date_from',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail(request):
    return _page(
        request,
        title='Kế hoạch chi tiết',
        subtitle='KHCT — phân bổ theo ngày (demo).',
        model=SxDetailPlan,
        fields=['code', 'name', 'date_from', 'date_to', '_status'],
        labels=['Mã', 'Tên', 'Từ', 'Đến', 'Trạng thái'],
        related_url_name='san_xuat:plan_overall',
        order_by='-date_from',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_npl(request):
    return _page(
        request,
        title='Kế hoạch nguyên phụ liệu',
        subtitle='KHNVL — nhu cầu NVL theo BOM × kế hoạch (demo, không ghi kho).',
        model=SxMaterialPlan,
        fields=['code', 'name', '_status', 'created_at'],
        labels=['Mã', 'Tên', 'Trạng thái', 'Ngày tạo'],
        related_url_name='san_xuat:doc_list',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_purchase_request(request):
    return _page(
        request,
        title='Yêu cầu mua nguyên phụ liệu',
        subtitle='YCM — yêu cầu mua nội bộ (demo, không tạo phiếu kho).',
        model=SxNplPurchaseRequest,
        fields=['code', 'due_date', '_status', 'created_at'],
        labels=['Mã', 'Hạn', 'Trạng thái', 'Ngày tạo'],
        related_url_name='san_xuat:plan_npl',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def purchase_order(request):
    return _page(
        request,
        title='Đơn mua hàng',
        subtitle='DMH nội bộ (demo). Tham khảo phiếu nhập KV qua menu KiotViet.',
        model=SxPurchaseOrder,
        fields=['code', 'supplier_name', '_status', 'created_at'],
        labels=['Mã', 'NCC', 'Trạng thái', 'Ngày tạo'],
        related_url_name='kiotviet:purchase_lookup',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_stub(request):
    return render(request, 'san_xuat/hub_dispatch.html', {**_perm_ctx(request)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo(request):
    return _page(
        request,
        title='Lệnh sản xuất',
        subtitle='LSX — lệnh sản xuất theo kế hoạch (demo).',
        model=SxProductionOrder,
        fields=['code', 'product_code', 'qty', 'due_date', '_status'],
        labels=['Mã LSX', 'Mã SP', 'SL', 'Hạn', 'Trạng thái'],
        related_url_name='san_xuat:plan_detail',
        order_by='-order_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_disassembly(request):
    return _page(
        request,
        title='Lệnh tháo dỡ',
        subtitle='LTD — tháo dỡ TP/BTP (demo).',
        model=SxDisassemblyOrder,
        fields=['code', 'product_code', 'qty', 'order_date', '_status'],
        labels=['Mã', 'Mã SP', 'SL', 'Ngày', 'Trạng thái'],
        order_by='-order_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_schedule(request):
    return _page(
        request,
        title='Lịch sản xuất',
        subtitle='Lịch đọc từ LSX — planned start/end (demo).',
        model=SxProductionOrder,
        fields=['code', 'product_code', 'planned_start', 'planned_end', 'team_label'],
        labels=['LSX', 'Mã SP', 'Bắt đầu', 'Kết thúc', 'Tổ'],
        related_url_name='san_xuat:dispatch_mo',
        order_by='planned_start',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_material_issue_req(request):
    return _page(
        request,
        title='Yêu cầu xuất vật tư',
        subtitle='YCX — yêu cầu xuất cho LSX (demo, không tạo phiếu xuất kho).',
        model=SxMaterialIssueRequest,
        fields=['code', 'request_date', '_status', 'created_at'],
        labels=['Mã', 'Ngày YC', 'Trạng thái', 'Tạo'],
        related_url_name='san_xuat:dispatch_mo',
        order_by='-request_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_prod_stats(request):
    return _page(
        request,
        title='Thống kê sản xuất',
        subtitle='TKSX — sản lượng đạt/lỗi theo ngày (demo).',
        model=SxProductionStat,
        fields=['code', 'stat_date', 'process_name', 'qty_good', 'qty_defect'],
        labels=['Mã', 'Ngày', 'Công đoạn', 'Đạt', 'Lỗi'],
        related_url_name='san_xuat:dispatch_mo',
        order_by='-stat_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_fg_receipt_req(request):
    return _page(
        request,
        title='Yêu cầu nhập thành phẩm',
        subtitle='YCNTP — yêu cầu nhập TP sau LSX (demo).',
        model=SxFgReceiptRequest,
        fields=['code', 'request_date', 'qty', '_status'],
        labels=['Mã', 'Ngày', 'SL', 'Trạng thái'],
        related_url_name='san_xuat:dispatch_mo',
        order_by='-request_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_npl_surplus(request):
    return _page(
        request,
        title='NPL thừa',
        subtitle='Ghi nhận NPL thừa sau SX (demo, không nhập kho).',
        model=SxNplSurplus,
        fields=['code', 'material_code', 'qty', 'recorded_at'],
        labels=['Mã', 'NVL', 'SL thừa', 'Ngày'],
        related_url_name='san_xuat:dispatch_mo',
        order_by='-recorded_at',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_handover(request):
    return _page(
        request,
        title='Bàn giao bán thành phẩm',
        subtitle='Bàn giao BTP giữa công đoạn (demo).',
        model=SxWipHandover,
        fields=['code', 'from_process', 'to_process', 'qty', '_status'],
        labels=['Mã', 'Từ CĐ', 'Đến CĐ', 'SL', 'Trạng thái'],
        related_url_name='san_xuat:dispatch_handover_status',
        order_by='-handover_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_return(request):
    return _page(
        request,
        title='Trả lại bán thành phẩm',
        subtitle='Trả BTP về công đoạn trước (demo).',
        model=SxWipReturn,
        fields=['code', 'return_date', 'qty', 'reason'],
        labels=['Mã', 'Ngày', 'SL', 'Lý do'],
        related_url_name='san_xuat:dispatch_wip_handover',
        order_by='-return_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_handover_status(request):
    return _page(
        request,
        title='Tình hình bàn giao SX',
        subtitle='Tổng hợp trạng thái bàn giao BTP (demo).',
        model=SxWipHandover,
        fields=['code', 'production_order', 'handover_date', 'qty', '_status'],
        labels=['Mã', 'LSX', 'Ngày', 'SL', 'Trạng thái'],
        related_url_name='san_xuat:dispatch_stub',
        order_by='-handover_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_stub(request):
    return render(request, 'san_xuat/hub_qc.html', {**_perm_ctx(request)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_request(request):
    return _page(
        request,
        title='Yêu cầu kiểm tra',
        subtitle='YCKT — yêu cầu QC theo LSX (demo).',
        model=SxQcRequest,
        fields=['code', 'product_code', 'stage_name', 'qty', '_status'],
        labels=['Mã', 'Mã SP', 'Công đoạn', 'SL', 'Trạng thái'],
        related_url_name='san_xuat:qc_sheet',
        order_by='-request_date',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sheet(request):
    return _page(
        request,
        title='Phiếu kiểm tra',
        subtitle='PKT — kết quả QC (demo).',
        model=SxQcInspection,
        fields=['code', 'inspected_at', 'qty_pass', 'qty_fail', 'result'],
        labels=['Mã', 'Ngày KT', 'Đạt', 'Lỗi', 'Kết luận'],
        related_url_name='san_xuat:qc_request',
        order_by='-inspected_at',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_criteria(request):
    return _page(
        request,
        title='Tiêu chí chất lượng',
        subtitle='Danh mục tiêu chí QC (demo).',
        model=SxQcCriteria,
        fields=['code', 'name', 'group', 'kind'],
        labels=['Mã', 'Tên', 'Nhóm', 'Loại'],
        related_url_name='san_xuat:qc_criteria_group',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_criteria_group(request):
    return _page(
        request,
        title='Nhóm tiêu chí chất lượng',
        subtitle='Nhóm tiêu chí QC (demo).',
        model=SxQcCriteriaGroup,
        fields=['code', 'name', 'is_active'],
        labels=['Mã', 'Tên', 'Active'],
        related_url_name='san_xuat:qc_criteria',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sampling(request):
    return _page(
        request,
        title='Phương pháp chọn mẫu',
        subtitle='Quy tắc lấy mẫu QC (demo).',
        model=SxQcSamplingMethod,
        fields=['code', 'name', 'method_type', 'sample_value'],
        labels=['Mã', 'Tên', 'Loại', 'Giá trị'],
        related_url_name='san_xuat:qc_standard_set',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_standard_set(request):
    return _page(
        request,
        title='Bộ tiêu chuẩn kiểm tra chất lượng',
        subtitle='Bộ tiêu chuẩn áp dụng theo SP (demo).',
        model=SxQcStandardSet,
        fields=['code', 'name', 'product_code', 'sampling_method'],
        labels=['Mã', 'Tên', 'Mã SP', 'Chọn mẫu'],
        related_url_name='san_xuat:qc_sheet',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_defect(request):
    return _page(
        request,
        title='Lỗi kiểm tra chất lượng',
        subtitle='Danh mục mã lỗi QC (demo).',
        model=SxQcDefect,
        fields=['code', 'name', 'group', 'severity'],
        labels=['Mã', 'Tên', 'Nhóm', 'Mức độ'],
        related_url_name='san_xuat:qc_defect_group',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_defect_group(request):
    return _page(
        request,
        title='Nhóm lỗi kiểm tra chất lượng',
        subtitle='Nhóm lỗi QC (demo).',
        model=SxQcDefectGroup,
        fields=['code', 'name', 'is_active'],
        labels=['Mã', 'Tên', 'Active'],
        related_url_name='san_xuat:qc_defect',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def process_stub(request):
    steps = (
        ProcessStep.objects.filter(bom__tech_doc__notes__startswith='[DEMO SX]')
        .select_related('bom__tech_doc')
        .order_by('bom__tech_doc__product_code', 'sequence')[:100]
    )
    rows = []
    for step in steps:
        doc = step.bom.tech_doc
        rows.append({
            'cells': [
                doc.product_code,
                step.sequence,
                step.process_name,
                step.norm_per_hour,
                step.cost_per_hour,
            ],
        })
    return hub_list_page(
        request,
        perm_ctx=_perm_ctx(request),
        title='Quy trình',
        subtitle='Công đoạn từ hồ sơ SX demo — chi tiết sửa trong Hồ sơ.',
        columns=[{'label': x} for x in ['Mã SP', 'TT', 'Công đoạn', 'ĐM cái/giờ', 'CP giờ']],
        rows=rows,
        empty_hint=_DEMO_HINT,
        related_url_name='san_xuat:doc_list',
    )
