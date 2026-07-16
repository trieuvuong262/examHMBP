"""Nhúng tra cứu KiotViet (hàng hoá / tồn / phiếu nhập) vào hub Sản xuất."""

from __future__ import annotations

from functools import wraps

from django.shortcuts import render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT
from kiotviet import catalog_views

from san_xuat.views import _perm_ctx

SX_KV_EMBED_URLS = {
    'product_lookup': 'san_xuat:fg_product_lookup',
    'product_detail': 'san_xuat:fg_product_detail',
    'stock_lookup': 'san_xuat:fg_stock_lookup',
    'purchase_lookup': 'san_xuat:fg_purchase_lookup',
    'purchase_detail': 'san_xuat:fg_purchase_detail',
}


def _with_sx_kv_embed(view_func):
    @module_perm_required(MODULE_SAN_XUAT, 'view')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        request.kv_embed_urls = SX_KV_EMBED_URLS
        return view_func(request, *args, **kwargs)

    return wrapper


@module_perm_required(MODULE_SAN_XUAT, 'view')
def fg_stock_hub(request):
    """Landing Kho sản phẩm — lối tắt sang catalog KV nhúng."""
    return render(request, 'san_xuat/hub_fg.html', {
        **_perm_ctx(request),
    })


@_with_sx_kv_embed
def fg_product_lookup(request):
    return catalog_views.product_lookup(request)


@_with_sx_kv_embed
def fg_product_detail(request, product_id: int):
    return catalog_views.product_detail(request, product_id)


@_with_sx_kv_embed
def fg_stock_lookup(request):
    return catalog_views.stock_lookup(request)


@_with_sx_kv_embed
def fg_purchase_lookup(request):
    return catalog_views.purchase_lookup(request)


@_with_sx_kv_embed
def fg_purchase_detail(request, purchase_id: int):
    return catalog_views.purchase_detail(request, purchase_id)
