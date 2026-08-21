from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.models import StockBalance, StockLedger, StockReceipt
from kho_npl.services.batches import (
    BatchWorkflowError,
    auto_receipt_batch_code,
    increase_batch_qty,
    ledger_amount,
    resolve_or_create_receipt_batch,
)


class ReceiptWorkflowError(Exception):
    pass


def receipt_is_editable(receipt: StockReceipt) -> bool:
    return receipt.status == DOC_STATUS_DRAFT


@transaction.atomic
def post_stock_receipt(receipt: StockReceipt, user) -> StockReceipt:
    receipt = StockReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.status != DOC_STATUS_DRAFT:
        raise ReceiptWorkflowError('Chỉ phiếu đã tạo mới được nhập kho.')
    lines = list(receipt.lines.select_related('material', 'location').all())
    if not lines:
        raise ReceiptWorkflowError('Phiếu nhập chưa có dòng chi tiết.')
    if not receipt.attachment:
        raise ReceiptWorkflowError('Vui lòng đính kèm chứng từ trước khi nhập kho.')
    for line in lines:
        if line.received_qty <= Decimal('0'):
            raise ReceiptWorkflowError(f'Số lượng nhập của {line.material.code} phải lớn hơn 0.')
        batch_code = (line.batch_code or '').strip() or auto_receipt_batch_code(
            receipt_number=receipt.number,
            material=line.material,
        )
        if line.unit_price is None or line.unit_price < 0:
            raise ReceiptWorkflowError(f'{line.material.code}: đơn giá nhập không hợp lệ.')
        if line.unit_price <= 0:
            raise ReceiptWorkflowError(f'{line.material.code}: đơn giá nhập phải lớn hơn 0.')
        try:
            batch = resolve_or_create_receipt_batch(
                material=line.material,
                batch_code=batch_code,
                unit_price=line.unit_price,
                received_date=receipt.receipt_date,
            )
            increase_batch_qty(batch, line.received_qty)
        except BatchWorkflowError as exc:
            raise ReceiptWorkflowError(str(exc)) from exc

        line.batch_code = batch.code
        line.save(update_fields=['batch_code'])

        balance, _ = StockBalance.objects.select_for_update().get_or_create(
            material=line.material,
            location=line.location,
            defaults={'quantity': Decimal('0')},
        )
        balance.quantity += line.received_qty
        balance.save(update_fields=['quantity', 'updated_at'])
        StockLedger.objects.create(
            material=line.material,
            location=line.location,
            qty_delta=line.received_qty,
            balance_after=balance.quantity,
            batch=batch,
            unit_price=line.unit_price,
            amount=ledger_amount(line.received_qty, line.unit_price),
            ref_type=StockLedger.REF_RECEIPT,
            ref_id=receipt.pk,
            ref_number=receipt.number,
            created_by=user,
            notes=f'Nhập kho {receipt.number}',
        )
    receipt.status = DOC_STATUS_POSTED
    receipt.posted_at = timezone.now()
    receipt.save(update_fields=['status', 'posted_at'])
    return receipt


@transaction.atomic
def cancel_stock_receipt(receipt: StockReceipt) -> StockReceipt:
    receipt = StockReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.status != DOC_STATUS_DRAFT:
        raise ReceiptWorkflowError('Chỉ phiếu đã tạo mới được hủy.')
    receipt.status = DOC_STATUS_CANCELLED
    receipt.save(update_fields=['status'])
    return receipt
