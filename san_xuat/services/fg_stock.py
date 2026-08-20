"""Ghi tăng tồn thành phẩm khi Yêu cầu nhập thành phẩm hoàn thành.

Central là app trong cùng Portal nên đây là lời gọi hàm trực tiếp trong **cùng
transaction** với việc chuyển phiếu sang ``done`` — không outbox, không HTTP,
không có trạng thái "đã nhập kho nhưng tồn chưa ghi".

Thiết kế: docs/integrations/central-product/inventory-schema.md (mục 7)
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from kho_san_pham.choices import (
    DOC_TYPE_FG_RECEIPT,
    MOVEMENT_PRODUCTION_IN,
    SOURCE_SYSTEM_PORTAL,
    WAREHOUSE_OWNER_PORTAL,
)
from kho_san_pham.models import Product, Warehouse
from kho_san_pham.services.stock import RESULT_APPLIED, StockMovementError, post_movement


class FgStockError(Exception):
    """Không ghi được tồn — chặn việc hoàn thành phiếu.

    Cố ý chặn: để phiếu ``done`` mà tồn không tăng thì kho sản phẩm sai ngay,
    và không có gì báo cho ai biết.
    """


@dataclass
class FgStockResult:
    posted: int = 0
    already: int = 0
    missing_cost: int = 0
    lines: list = field(default_factory=list)


def resolve_product_for_line(line) -> Product:
    """Tìm SKU trong kho sản phẩm ứng với một dòng YCNTP.

    Ưu tiên FK ``line.sku`` (SxSku) vì đó là liên kết chắc; dữ liệu thực tế lại
    hay để trống FK và chỉ có ``sku_code``, nên phải có cả đường thứ hai.
    """
    if line.sku_id:
        matches = list(Product.objects.filter(sx_sku_id=line.sku_id)[:2])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise FgStockError(
                f'SKU sản xuất {line.sku_code or line.sku_id} đang trỏ tới nhiều sản phẩm '
                'trong kho sản phẩm — phải gộp trước khi nhập kho.'
            )

    code = (line.sku_code or '').strip().upper()
    if not code:
        raise FgStockError(
            f'Dòng nhập thành phẩm #{line.pk} không có SKU — không biết ghi tăng tồn cho mã nào.'
        )

    product = Product.objects.filter(code=code).first()
    if product is None:
        raise FgStockError(
            f'SKU {code} không có trong kho sản phẩm. Tạo SKU trong danh mục trước khi nhập kho.'
        )
    return product


def resolve_fg_warehouse(receipt) -> Warehouse:
    """Kho nhận thành phẩm của phiếu.

    Phiếu cũ chỉ có ``warehouse_code`` chữ tự do (kiểu ``kv:4``), nên khi thiếu
    FK thì lùi về kho thành phẩm duy nhất của Portal.
    """
    if receipt.warehouse_id:
        return receipt.warehouse

    portal_warehouses = list(
        Warehouse.objects.filter(is_active=True, owner_system=WAREHOUSE_OWNER_PORTAL)[:2]
    )
    if len(portal_warehouses) == 1:
        return portal_warehouses[0]
    if not portal_warehouses:
        raise FgStockError(
            'Chưa có kho thành phẩm nào. Chạy "manage.py kho_sp_seed_warehouses --apply" trước.'
        )
    raise FgStockError(
        f'Phiếu {receipt.code} chưa chọn kho nhập mà hệ có nhiều kho thành phẩm — phải chọn rõ kho.'
    )


def resolve_unit_cost(receipt) -> Decimal | None:
    """Giá thành một sản phẩm, hoặc ``None`` khi chưa tính được.

    ``None`` khác 0: chưa biết giá thì để trống để còn điền bù, ghi 0 là khẳng
    định sai rằng sản phẩm không có chi phí.
    """
    mo = receipt.production_order
    product_code = (getattr(mo, 'product_code', '') or '').strip()
    if not product_code:
        return None

    from san_xuat.services.plan_costing import resolve_unit_standard_cost

    try:
        cost = resolve_unit_standard_cost(product_code)
    except Exception:
        # Giá thành chưa dựng xong không được làm nhập kho thất bại.
        return None
    if cost is None or cost <= 0:
        return None
    return Decimal(cost).quantize(Decimal('0.01'))


def post_fg_receipt_to_stock(receipt, *, user=None) -> FgStockResult:
    """Ghi tăng tồn cho mọi dòng của một YCNTP đã hoàn thành.

    Gọi lại nhiều lần vô hại: khóa chống trùng của sổ kho là
    ``(portal, fg_receipt, mã phiếu, id dòng)`` nên lần sau trả ``already``.
    """
    from san_xuat.hub_models import SxFgReceiptRequest

    if receipt.status != SxFgReceiptRequest.STATUS_DONE:
        raise FgStockError(
            f'Chỉ ghi tồn khi phiếu {receipt.code} đã hoàn thành (đang: {receipt.status}).'
        )

    warehouse = resolve_fg_warehouse(receipt)
    unit_cost = resolve_unit_cost(receipt)

    lines = [ln for ln in receipt.lines.all() if (ln.qty or Decimal('0')) > 0]
    if not lines:
        raise FgStockError(
            f'Phiếu {receipt.code} không có dòng SKU nào có số lượng — '
            'không biết ghi tăng tồn cho mã nào.'
        )

    result = FgStockResult()
    actor = getattr(user, 'username', '') or ''

    for line in lines:
        product = resolve_product_for_line(line)
        qty = Decimal(line.qty).quantize(Decimal('0.01'))
        try:
            movement = post_movement(
                product=product,
                warehouse=warehouse,
                kind=MOVEMENT_PRODUCTION_IN,
                qty_delta=qty,
                unit_cost=unit_cost,
                source_system=SOURCE_SYSTEM_PORTAL,
                source_doc_type=DOC_TYPE_FG_RECEIPT,
                source_doc_code=receipt.code,
                # id dòng, không phải số thứ tự: số thứ tự đổi khi sửa dòng, và
                # khi đó lần ghi sau sẽ bị coi là phát sinh mới.
                source_line_no=line.pk,
                occurred_at=_occurred_at(receipt),
                created_by=user if getattr(user, 'pk', None) else None,
                actor=actor,
                notes=f'Nhập thành phẩm {receipt.code}',
            )
        except StockMovementError as exc:
            raise FgStockError(f'{product.code}: {exc}') from exc

        if movement.status == RESULT_APPLIED:
            result.posted += 1
        else:
            result.already += 1
        if unit_cost is None:
            result.missing_cost += 1
        result.lines.append((product.code, qty, movement.status))

    return result


def _occurred_at(receipt):
    """Thời điểm nghiệp vụ = ngày ghi trên phiếu, không phải lúc bấm nút.

    Phiếu lập ngày 11/08 mà bấm hoàn thành ngày 20/08 thì phát sinh phải thuộc
    ngày 11/08, nếu không báo cáo sản lượng theo ngày sẽ lệch.
    """
    if receipt.request_date is None:
        return timezone.now()
    naive = datetime.combine(receipt.request_date, time.min)
    return timezone.make_aware(naive) if settings.USE_TZ else naive
