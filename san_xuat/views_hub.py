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
def redirect_fg_stock(request):
    return redirect('kiotviet:stock_lookup')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_npl_stock(request):
    return redirect('kho_npl:material_stock')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def redirect_costing(request):
    """Giá thành kế hoạch → hồ sơ SX (costing tab đã có trong hồ sơ)."""
    return redirect('san_xuat:doc_list')


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
    return _stub(
        request,
        title='Kế hoạch sản xuất',
        subtitle='SO → kế hoạch → lệnh sản xuất (LSX). Scaffold — chưa lưu DB.',
        next_steps=[
            'Lấy đơn từ KiotViet (menu Đơn đặt hàng).',
            'Lập kế hoạch theo mã SP / số lượng.',
            'Phát LSX và điều phối tổ chuyền (phase sau).',
        ],
        related_url_name='san_xuat:redirect_orders',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def dispatch_stub(request):
    return _stub(
        request,
        title='Điều phối',
        subtitle='Gán kế hoạch / LSX theo tổ, ngày, ca. Scaffold placeholder.',
        next_steps=[
            'Bảng điều phối theo tổ / ngày.',
            'Liên kết lệnh sản xuất (phase sau).',
        ],
        related_url_name='san_xuat:plan_stub',
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def qc_stub(request):
    return _stub(
        request,
        title='Kiểm tra chất lượng',
        subtitle='Phiếu QC theo lô / LSX. Scaffold — chưa dùng Odoo Quality.',
        next_steps=[
            'Ghi nhận đạt / không đạt theo mã SP.',
            'Gắn với kế hoạch hoặc hồ sơ SX (phase sau).',
        ],
        related_url_name='san_xuat:doc_list',
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
