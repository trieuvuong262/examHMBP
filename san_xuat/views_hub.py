"""Hub Sản xuất — overview, stub pages, deep-link redirects.

Không đụng nghiệp vụ kho_npl / kiotviet; chỉ redirect hoặc trang placeholder.
"""

from __future__ import annotations

from django.shortcuts import redirect, render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT

from san_xuat.models import ProductTechDoc
from san_xuat.views import _perm_ctx


@module_perm_required(MODULE_SAN_XUAT, 'view')
def overview(request):
    """Tổng quan hub — KPI nhẹ, link nhanh."""
    doc_total = ProductTechDoc.objects.count()
    doc_active = ProductTechDoc.objects.filter(is_active=True).count()
    return render(request, 'san_xuat/hub_overview.html', {
        **_perm_ctx(request),
        'doc_total': doc_total,
        'doc_active': doc_active,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_orders(request):
    return redirect('kiotviet:order_lookup')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_npl_stock(request):
    return redirect('kho_npl:material_stock')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_costing(request):
    """Landing giá thành kế hoạch (giữ tên URL cũ)."""
    return render(request, 'san_xuat/hub_costing.html', {
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_norm(request):
    return _stub(
        request,
        title='Giá thành định mức sản phẩm',
        subtitle='Costing theo BOM / định mức NVL + nhân công trên mã SP. Scaffold.',
        next_steps=[
            'Lấy định mức từ Hồ sơ SX (BOM + Costing đã có).',
            'Chuẩn hóa bảng giá thành định mức theo mã hàng (phase sau).',
        ],
        related_url_name='san_xuat:doc_list',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def costing_by_order(request):
    return _stub(
        request,
        title='Giá thành kế hoạch theo đơn đặt hàng',
        subtitle='Costing kế hoạch = định mức × SL đơn hàng. Scaffold.',
        next_steps=[
            'Chọn đơn KiotViet / SO.',
            'Nhân định mức SP với số lượng đơn → giá thành kế hoạch (phase sau).',
        ],
        related_url_name='san_xuat:redirect_orders',
    )


def _stub(request, *, title: str, subtitle: str, next_steps: list[str], related_url_name: str | None = None):
    return render(request, 'san_xuat/hub_stub.html', {
        **_perm_ctx(request),
        'hub_title': title,
        'hub_subtitle': subtitle,
        'next_steps': next_steps,
        'related_url_name': related_url_name,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_stub(request):
    """Landing nhóm kế hoạch — liệt kê 5 menu con."""
    return render(request, 'san_xuat/hub_plan.html', {
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_overall(request):
    return _stub(
        request,
        title='Kế hoạch tổng thể',
        subtitle='Khung kế hoạch SX theo kỳ / đơn hàng (tháng, tuần). Scaffold.',
        next_steps=[
            'Tổng hợp đơn khách → khối lượng SX theo mã SP.',
            'Phân bổ theo tuần / chuyền (phase sau).',
        ],
        related_url_name='san_xuat:redirect_orders',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_detail(request):
    return _stub(
        request,
        title='Kế hoạch chi tiết',
        subtitle='Chi tiết theo ngày / tổ / LSX. Scaffold.',
        next_steps=[
            'Bóc tách kế hoạch tổng thể thành lịch chi tiết.',
            'Liên kết điều phối và hồ sơ BOM (phase sau).',
        ],
        related_url_name='san_xuat:plan_overall',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def plan_npl(request):
    return _stub(
        request,
        title='Kế hoạch nguyên phụ liệu',
        subtitle='Nhu cầu NPL theo BOM × kế hoạch SX. Scaffold.',
        next_steps=[
            'Tính nhu cầu từ BOM active × SL kế hoạch.',
            'Đối chiếu tồn kho NPL Portal (SoT).',
        ],
        related_url_name='san_xuat:redirect_npl_stock',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def npl_purchase_request(request):
    return _stub(
        request,
        title='Yêu cầu mua nguyên phụ liệu',
        subtitle='PR mua NPL từ thiếu hụt kế hoạch NPL. Scaffold — chưa tạo phiếu.',
        next_steps=[
            'Sinh yêu cầu mua từ kế hoạch NPL / cảnh báo tồn.',
            'Duyệt PR → tạo đơn mua (phase sau).',
        ],
        related_url_name='san_xuat:plan_npl',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def purchase_order(request):
    """Đơn mua hàng — stub + lối tắt phiếu nhập KiotViet (tham khảo)."""
    return _stub(
        request,
        title='Đơn mua hàng',
        subtitle='PO mua NPL / hàng. Scaffold. Có thể xem phiếu nhập KiotViet hiện có.',
        next_steps=[
            'Quản lý đơn mua nội bộ (phase sau).',
            'Tham khảo phiếu nhập đã sync từ KiotViet.',
        ],
        related_url_name='kiotviet:purchase_lookup',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_stub(request):
    """Landing nhóm điều phối — liệt kê menu con."""
    return render(request, 'san_xuat/hub_dispatch.html', {
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_mo(request):
    return _stub(
        request,
        title='Lệnh sản xuất',
        subtitle='LSX / MO theo kế hoạch chi tiết. Scaffold.',
        next_steps=['Tạo / theo dõi lệnh sản xuất theo mã SP.', 'Liên kết lịch SX và xuất vật tư (phase sau).'],
        related_url_name='san_xuat:plan_detail',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_disassembly(request):
    return _stub(
        request,
        title='Lệnh tháo dỡ',
        subtitle='Tháo dỡ thành phẩm / bán thành phẩm về NPL. Scaffold.',
        next_steps=['Tạo lệnh tháo dỡ.', 'Ghi nhận NPL thu hồi về kho (phase sau).'],
        related_url_name='san_xuat:redirect_npl_stock',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_schedule(request):
    return _stub(
        request,
        title='Lịch sản xuất',
        subtitle='Lịch theo ngày / tổ / chuyền. Scaffold.',
        next_steps=['Xếp lịch từ kế hoạch chi tiết.', 'Đồng bộ với lệnh sản xuất (phase sau).'],
        related_url_name='san_xuat:dispatch_mo',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_material_issue_req(request):
    return _stub(
        request,
        title='Yêu cầu xuất vật tư',
        subtitle='Yêu cầu xuất NPL cho LSX. Scaffold — SoT xuất kho vẫn trên Portal kho_npl.',
        next_steps=['Sinh yêu cầu từ LSX / BOM.', 'Sau duyệt → phiếu xuất kho_npl (phase sau).'],
        related_url_name='kho_npl:issue_list',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_prod_stats(request):
    return _stub(
        request,
        title='Thống kê sản xuất',
        subtitle='Sản lượng / tiến độ theo kỳ. Scaffold.',
        next_steps=['Tổng hợp từ LSX và bàn giao.', 'Báo cáo theo tổ / mã SP (phase sau).'],
        related_url_name='san_xuat:dispatch_stub',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_fg_receipt_req(request):
    return _stub(
        request,
        title='Yêu cầu nhập thành phẩm',
        subtitle='Yêu cầu nhập TP sau hoàn thành LSX. Scaffold.',
        next_steps=['Tạo yêu cầu nhập từ LSX hoàn thành.', 'Đối chiếu kho thành phẩm / KiotViet (phase sau).'],
        related_url_name='san_xuat:redirect_fg_stock',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_npl_surplus(request):
    return _stub(
        request,
        title='NPL thừa',
        subtitle='Theo dõi NPL thừa sau SX / tháo dỡ. Scaffold.',
        next_steps=['Ghi nhận thừa theo LSX.', 'Nhập lại kho NPL (phase sau).'],
        related_url_name='san_xuat:redirect_npl_stock',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_handover(request):
    return _stub(
        request,
        title='Bàn giao bán thành phẩm',
        subtitle='Bàn giao BTP giữa các công đoạn / tổ. Scaffold.',
        next_steps=['Tạo phiếu bàn giao BTP.', 'Theo dõi tình hình bàn giao SX.'],
        related_url_name='san_xuat:dispatch_handover_status',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_wip_return(request):
    return _stub(
        request,
        title='Trả lại bán thành phẩm',
        subtitle='Trả BTP về công đoạn trước / kho. Scaffold.',
        next_steps=['Tạo phiếu trả lại BTP.', 'Cập nhật tình hình bàn giao.'],
        related_url_name='san_xuat:dispatch_wip_handover',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_handover_status(request):
    return _stub(
        request,
        title='Tình hình bàn giao SX',
        subtitle='Tổng hợp trạng thái bàn giao / trả lại BTP. Scaffold.',
        next_steps=['Dashboard tiến độ bàn giao theo LSX / tổ.', 'Cảnh báo chậm bàn giao (phase sau).'],
        related_url_name='san_xuat:dispatch_stub',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_stub(request):
    """Landing nhóm QC — yêu cầu / phiếu / danh mục tiêu chuẩn."""
    return render(request, 'san_xuat/hub_qc.html', {
        **_perm_ctx(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_request(request):
    return _stub(
        request,
        title='Yêu cầu kiểm tra',
        subtitle='Yêu cầu QC theo LSX / lô / công đoạn. Scaffold.',
        next_steps=['Tạo yêu cầu kiểm tra từ LSX hoặc bàn giao.', 'Sinh phiếu kiểm tra (phase sau).'],
        related_url_name='san_xuat:qc_sheet',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sheet(request):
    return _stub(
        request,
        title='Phiếu kiểm tra',
        subtitle='Phiếu ghi kết quả QC theo bộ tiêu chuẩn. Scaffold.',
        next_steps=['Nhập kết quả theo tiêu chí / lỗi.', 'Kết luận đạt / không đạt (phase sau).'],
        related_url_name='san_xuat:qc_request',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_criteria(request):
    return _stub(
        request,
        title='Tiêu chí chất lượng',
        subtitle='Danh mục tiêu chí đo / đánh giá. Scaffold.',
        next_steps=['Khai báo tiêu chí (định tính / định lượng).', 'Gắn vào nhóm tiêu chí và bộ tiêu chuẩn.'],
        related_url_name='san_xuat:qc_criteria_group',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_criteria_group(request):
    return _stub(
        request,
        title='Nhóm tiêu chí chất lượng',
        subtitle='Nhóm hóa tiêu chí theo công đoạn / loại SP. Scaffold.',
        next_steps=['Tạo nhóm tiêu chí.', 'Gán tiêu chí vào nhóm.'],
        related_url_name='san_xuat:qc_criteria',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_sampling(request):
    return _stub(
        request,
        title='Phương pháp chọn mẫu',
        subtitle='Quy tắc lấy mẫu (AQL, tỷ lệ, 100%, …). Scaffold.',
        next_steps=['Khai báo phương pháp chọn mẫu.', 'Gắn vào bộ tiêu chuẩn kiểm tra.'],
        related_url_name='san_xuat:qc_standard_set',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_standard_set(request):
    return _stub(
        request,
        title='Bộ tiêu chuẩn kiểm tra chất lượng',
        subtitle='Tập tiêu chí + phương pháp mẫu áp dụng theo mã SP / công đoạn. Scaffold.',
        next_steps=['Tạo bộ tiêu chuẩn.', 'Gắn nhóm tiêu chí, phương pháp mẫu, nhóm lỗi.'],
        related_url_name='san_xuat:qc_sheet',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_defect(request):
    return _stub(
        request,
        title='Lỗi kiểm tra chất lượng',
        subtitle='Danh mục mã lỗi / mức độ lỗi. Scaffold.',
        next_steps=['Khai báo lỗi QC.', 'Gán vào nhóm lỗi.'],
        related_url_name='san_xuat:qc_defect_group',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_defect_group(request):
    return _stub(
        request,
        title='Nhóm lỗi kiểm tra chất lượng',
        subtitle='Nhóm hóa lỗi theo loại / công đoạn. Scaffold.',
        next_steps=['Tạo nhóm lỗi.', 'Dùng khi ghi phiếu kiểm tra.'],
        related_url_name='san_xuat:qc_defect',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def process_stub(request):
    return _stub(
        request,
        title='Quy trình',
        subtitle='Công đoạn định mức theo mã hàng. Công đoạn chi tiết đang nằm trong Hồ sơ SX.',
        next_steps=[
            'Xem / sửa công đoạn trong Hồ sơ SX → tab Quy trình.',
            'Sau này có thể sync routing sang Odoo MRP.',
        ],
        related_url_name='san_xuat:doc_list',
    )
