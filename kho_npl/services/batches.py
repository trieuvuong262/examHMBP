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
    """Nhãn lô: mã — tồn kèm ĐVT — giá. VD: TON-DAU — 200 gói — 15.000đ."""
    from kho_npl.catalog_labels import unit_label
    from kho_npl.templatetags.npl_extras import format_npl_money, format_npl_qty

    price = batch_effective_price(batch)
    qty_text = format_npl_qty(batch.quantity or Decimal('0'))
    unit = unit_label(getattr(batch.material, 'unit', None))
    if unit:
        qty_text = f'{qty_text} {unit}'
    return f'{batch.code} — {qty_text} — {format_npl_money(price)}'


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


def material_avg_price(material: Material) -> Decimal:
    """
    Đơn giá BQ = trung bình cộng giá của tất cả các lô đã nhập (mọi phiếu nhập,
    kể cả lô đã hết tồn) cộng thêm giá cơ bản trong danh mục nếu có.
    Giá cơ bản trống (0) thì chỉ tính trung bình từ các lô.
    """
    prices = list(
        MaterialBatch.objects.filter(
            material=material,
            unit_price__gt=0,
        ).values_list('unit_price', flat=True)
    )
    base_price = material.base_price or Decimal('0')
    if base_price > 0:
        prices.append(base_price)
    if not prices:
        return Decimal('0')
    total = sum(prices, Decimal('0'))
    return (total / len(prices)).quantize(Decimal('0.01'))


def material_batch_totals(material: Material) -> tuple[Decimal, Decimal, Decimal]:
    """
    Trả (tổng tồn lô, tổng giá trị tồn, đơn giá BQ).

    Giá trị tồn = Σ(tồn lô × giá lô) — chỉ tính lô còn tồn.
    Đơn giá BQ = trung bình cộng giá tất cả lô + giá cơ bản (xem material_avg_price).
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
    avg_price = material_avg_price(material)
    if total_qty <= 0:
        return Decimal('0'), Decimal('0'), avg_price
    return total_qty, total_value.quantize(Decimal('0.01')), avg_price


def avg_cost(material: Material) -> Decimal:
    """Đơn giá BQ — trung bình cộng giá các lô + giá cơ bản danh mục."""
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
    """Cộng hoặc trừ tồn lô theo chênh lệch kiểm kê."""
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


AUTO_BATCH_CODE = 'AUTO'


def auto_receipt_batch_code(*, receipt_number: str, material: Material) -> str:
    """Mã lô tự sinh khi phiếu nhập không còn nhập tay."""
    code = f'{receipt_number}-{material.code}'.strip().upper()
    return code[:60]


def allocate_batches_fifo(
    material: Material,
    qty_needed: Decimal,
) -> list[tuple[MaterialBatch, Decimal]]:
    """Phân bổ SL theo FIFO các lô còn tồn (có thể nhiều lô)."""
    if qty_needed <= 0:
        raise BatchWorkflowError(f'{material.code}: số lượng phân bổ lô phải lớn hơn 0.')
    remaining = qty_needed
    allocations: list[tuple[MaterialBatch, Decimal]] = []
    for batch in batches_with_stock(material, include_zero=False):
        if remaining <= 0:
            break
        take = batch.quantity if batch.quantity < remaining else remaining
        if take > 0:
            allocations.append((batch, take))
            remaining -= take
    if remaining > 0:
        raise BatchWorkflowError(
            f'Không đủ tồn theo lô cho {material.code}: thiếu {remaining} (cần {qty_needed}).'
        )
    return allocations


def resolve_outflow_batches(
    material: Material,
    qty: Decimal,
    preferred_batch: MaterialBatch | None = None,
) -> list[tuple[MaterialBatch, Decimal]]:
    """Xuất/hủy: dùng lô đã chọn (nếu có) hoặc FIFO tự động."""
    if preferred_batch is not None:
        batch = validate_batch_for_material(preferred_batch, material)
        return [(batch, qty)]
    return allocate_batches_fifo(material, qty)


def resolve_inflow_batch(
    material: Material,
    *,
    preferred_batch: MaterialBatch | None = None,
    unit_price: Decimal | None = None,
    received_date=None,
) -> MaterialBatch:
    """Nhập tăng tồn (kiểm kê +): dùng lô đã chọn hoặc lô AUTO."""
    if preferred_batch is not None:
        return validate_batch_for_material(preferred_batch, material)
    price = unit_price if unit_price is not None else (material.base_price or Decimal('0'))
    if price is None or price < 0:
        price = Decimal('0')
    batch = (
        MaterialBatch.objects.select_for_update()
        .filter(material=material, code=AUTO_BATCH_CODE)
        .first()
    )
    if batch:
        if not batch.is_active:
            batch.is_active = True
            batch.save(update_fields=['is_active', 'updated_at'])
        return batch
    return MaterialBatch.objects.create(
        material=material,
        code=AUTO_BATCH_CODE,
        unit_price=price,
        received_date=received_date,
        quantity=Decimal('0'),
        is_active=True,
    )


def apply_variance_to_batches(
    material: Material,
    variance: Decimal,
    preferred_batch: MaterialBatch | None = None,
    *,
    received_date=None,
) -> list[tuple[MaterialBatch, Decimal]]:
    """
    Áp chênh lệch kiểm kê lên lô.
    Trả list (batch, qty_delta) đã áp — qty_delta cùng dấu với variance.
    """
    if variance == 0:
        return []
    if variance > 0:
        batch = resolve_inflow_batch(
            material,
            preferred_batch=preferred_batch,
            received_date=received_date,
        )
        increase_batch_qty(batch, variance)
        return [(batch, variance)]
    allocations = resolve_outflow_batches(material, abs(variance), preferred_batch)
    applied: list[tuple[MaterialBatch, Decimal]] = []
    for batch, take in allocations:
        decrease_batch_qty(batch, take, material_code=material.code)
        applied.append((batch, -take))
    return applied
