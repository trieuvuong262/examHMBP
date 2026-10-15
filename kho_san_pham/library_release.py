"""SKU của Style thiết kế chỉ vào Danh mục sau khi Thư viện chuyển sản xuất."""

from __future__ import annotations

from kho_san_pham.catalog_models import ProductStyle
from kho_san_pham.choices import STYLE_SOURCE_DESIGN


def held_style_codes():
    """Mã Style nguồn thiết kế chưa có hồ sơ sản xuất."""
    from thiet_ke_sp.models import Handover

    released = Handover.objects.filter(tech_doc__isnull=False).values('product_code')
    return ProductStyle.objects.filter(source=STYLE_SOURCE_DESIGN).exclude(code__in=released).values('code')


def exclude_held_library_products(qs):
    return qs.exclude(style_code__in=held_style_codes())


def style_transfer_block(code: str) -> str:
    """Chuỗi lỗi khi Style chưa có SKU đủ màu và size. Rỗng nếu chuyển được."""
    from kho_san_pham.models import Product

    qs = Product.objects.filter(style_code__iexact=(code or '').strip())
    if qs.exclude(color_code='').exclude(size_label='').exists():
        return ''
    if qs.exists():
        return 'Thêm size cho ít nhất một màu trong Thư viện trước khi chuyển sang sản xuất.'
    return 'Thư viện chưa có SKU. Thêm màu và size trước khi chuyển sang sản xuất.'


def is_held_library_style(code: str) -> bool:
    code = (code or '').strip().upper()
    if not code:
        return False
    if not ProductStyle.objects.filter(code=code, source=STYLE_SOURCE_DESIGN).exists():
        return False
    from thiet_ke_sp.models import Handover

    return not Handover.objects.filter(product_code=code, tech_doc__isnull=False).exists()
