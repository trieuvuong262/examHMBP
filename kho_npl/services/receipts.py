from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.models import StockBalance, StockLedger, StockReceipt


class ReceiptWorkflowError(Exception):
    pass


def receipt_is_editable(receipt: StockReceipt) -> bool:
    return receipt.status == DOC_STATUS_DRAFT


@transaction.atomic
def post_stock_receipt(receipt: StockReceipt, user) -> StockReceipt:
    receipt = StockReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.status != DOC_STATUS_DRAFT:
        raise ReceiptWorkflowError('Chỉ phiếu nháp mới được ghi sổ.')
    lines = list(receipt.lines.select_related('material', 'location').all())
    if not lines:
        raise ReceiptWorkflowError('Phiếu nhập chưa có dòng chi tiết.')
    for line in lines:
        if line.received_qty <= Decimal('0'):
            raise ReceiptWorkflowError(f'Số lượng nhập của {line.material.code} phải lớn hơn 0.')
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
        raise ReceiptWorkflowError('Chỉ phiếu nháp mới được hủy.')
    receipt.status = DOC_STATUS_CANCELLED
    receipt.save(update_fields=['status'])
    return receipt
