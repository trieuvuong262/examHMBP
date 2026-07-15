"""Quản lý lô hàng NPL — tồn theo lô, đơn giá, bình quân gia quyền."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F, Sum

from kho_npl.models import Material, MaterialBatch


class BatchWorkflowError(Exception):
    pass


def batches_with_stock(material: Material, *, include_zero: bool = False):
    """Danh sách lô của NPL (mặc định còn tồn)."""
    qs = MaterialBatch.objects.filter(material=material, is_active=True)
    if not include_zero:
        qs = qs.filter(quantity__gt=0)
    return qs.order_by('received_date', 'id')


def batch_effective_price(batch: MaterialBatch) -> Decimal:
    """Giá lô để tính thành tiền — lô chưa có giá (0) dùng giá cơ bản danh mục."""
    price = batch.unit_price or Decimal('0')
    if price > 0:
        return price
    return batch.material.base_price or Decimal('0')


def batch_label(batch: MaterialBatch) -> str:
    """Nhãn lô: mã — tồn kèm ĐVT — giá. VD: TON-DAU — 200 gói — 15.000₫."""
    from kho_npl.catalog_labels import unit_label
    from kho_npl.templatetags.npl_extras import format_npl_qty

    price = batch_effective_price(batch)
    price_text = f'{price:,.0f}'.replace(',', '.')
    qty_text = format_npl_qty(batch.quantity or Decimal('0'))
    unit = unit_label(getattr(batch.material, 'unit', None))
    if unit:
        qty_text = f'{qty_text} {unit}'
    return f'{batch.code} — {qty_text} — {price_text}₫'


def batch_stock_options(material: Material) -> list[dict]:
    """Options dropdown chọn lô (còn tồn)."""
    rows = []
    for batch in batches_with_stock(material).select_related('material__unit'):
        rows.append({
            'id': batch.pk,
            'code': batch.code,
            'unit_price': str(batch_effective_price(batch)),
            'quantity': str(batch.quantity),
            'label': batch_label(batch),
        })
    return rows


def material_batch_totals(material: Material) -> tuple[Decimal, Decimal, Decimal]:
    """
    Trả (tổng tồn lô, tổng giá trị, đơn giá bình quân gia quyền).
    Bỏ lô không còn tồn.
    """
    agg = MaterialBatch.objects.filter(
        material=material,
        is_active=True,
        quantity__gt=0,
    ).aggregate(
        total_qty=Sum('quantity'),
        total_value=Sum(F('quantity') * F('unit_price')),
    )
    total_qty = agg['total_qty'] or Decimal('0')
    total_value = agg['total_value'] or Decimal('0')
    if total_qty <= 0:
        return Decimal('0'), Decimal('0'), Decimal('0')
    avg_cost = (total_value / total_qty).quantize(Decimal('0.01'))
    return total_qty, total_value.quantize(Decimal('0.01')), avg_cost


def avg_cost(material: Material) -> Decimal:
    """Đơn giá bình quân gia quyền từ các lô còn tồn."""
    _qty, _value, avg = material_batch_totals(material)
    return avg


def stock_value(material: Material) -> Decimal:
    """Giá trị tồn = Σ(tồn lô × giá lô)."""
    _qty, value, _avg = material_batch_totals(material)
    return value


def ledger_amount(qty_delta: Decimal, unit_price: Decimal | None = None) -> Decimal:
    """Thành tiền trên sổ = |qty| × đơn giá (đơn giá mặc định 0)."""
    price = unit_price or Decimal('0')
    return (abs(qty_delta) * price).quantize(Decimal('0.01'))


def resolve_or_create_receipt_batch(
    *,
    material: Material,
    batch_code: str,
    unit_price: Decimal,
    received_date=None,
) -> MaterialBatch:
    """
    Lấy hoặc tạo lô từ dòng phiếu nhập.
    Nếu lô đã tồn tại với giá khác → lỗi.
    """
    code = (batch_code or '').strip().upper()
    if not code:
        raise BatchWorkflowError(f'{material.code}: chưa nhập mã lô.')
    if unit_price is None or unit_price < 0:
        raise BatchWorkflowError(f'{material.code}: đơn giá nhập không hợp lệ.')

    batch = (
        MaterialBatch.objects.select_for_update()
        .filter(material=material, code=code)
        .first()
    )
    if batch:
        if batch.unit_price != unit_price:
            raise BatchWorkflowError(
                f'{material.code}: lô {code} đã tồn tại với giá {batch.unit_price}, '
                f'không thể nhập thêm với giá {unit_price}.'
            )
        if not batch.is_active:
            batch.is_active = True
            batch.save(update_fields=['is_active', 'updated_at'])
        return batch

    return MaterialBatch.objects.create(
        material=material,
        code=code,
        unit_price=unit_price,
        received_date=received_date,
        quantity=Decimal('0'),
        is_active=True,
    )


def increase_batch_qty(batch: MaterialBatch, qty: Decimal) -> MaterialBatch:
    if qty <= 0:
        raise BatchWorkflowError('Số lượng cộng vào lô phải lớn hơn 0.')
    batch = MaterialBatch.objects.select_for_update().get(pk=batch.pk)
    batch.quantity += qty
    batch.save(update_fields=['quantity', 'updated_at'])
    return batch


def decrease_batch_qty(batch: MaterialBatch, qty: Decimal, *, material_code: str = '') -> MaterialBatch:
    if qty <= 0:
        raise BatchWorkflowError('Số lượng trừ lô phải lớn hơn 0.')
    batch = MaterialBatch.objects.select_for_update().get(pk=batch.pk)
    if batch.quantity < qty:
        label = material_code or (batch.material.code if batch.material_id else '')
        raise BatchWorkflowError(
            f'Tồn lô không đủ: {label} / {batch.code} '
            f'(có {batch.quantity}, cần {qty}).'
        )
    batch.quantity -= qty
    batch.save(update_fields=['quantity', 'updated_at'])
    return batch


def adjust_batch_qty(batch: MaterialBatch, qty_delta: Decimal, *, material_code: str = '') -> MaterialBatch:
    """Cộng hoặc trừ tồn lô theo chênh lệch điều chỉnh/kiểm kê."""
    if qty_delta == 0:
        return batch
    if qty_delta > 0:
        return increase_batch_qty(batch, qty_delta)
    return decrease_batch_qty(batch, abs(qty_delta), material_code=material_code)


def validate_batch_for_material(batch: MaterialBatch | None, material: Material) -> MaterialBatch:
    if not batch:
        raise BatchWorkflowError(f'{material.code}: chưa chọn lô hàng.')
    if batch.material_id != material.pk:
        raise BatchWorkflowError(f'Lô {batch.code} không thuộc {material.code}.')
    return batch
