from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import (
    TRANSFER_STATUS_CANCELLED,
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
)
from kho_npl.models import StockBalance, StockLedger, StockTransfer
from kho_npl.services.batches import ledger_amount


class TransferWorkflowError(Exception):
    pass


def transfer_is_editable(transfer: StockTransfer) -> bool:
    return transfer.status == TRANSFER_STATUS_DRAFT


def transfer_attachment_editable_after_send(transfer: StockTransfer) -> bool:
    return transfer.status in (TRANSFER_STATUS_IN_TRANSIT, TRANSFER_STATUS_RECEIVED)


def transfer_can_send(transfer: StockTransfer) -> bool:
    return transfer.status == TRANSFER_STATUS_DRAFT


def transfer_can_receive(transfer: StockTransfer) -> bool:
    return transfer.status == TRANSFER_STATUS_IN_TRANSIT


@transaction.atomic
def send_stock_transfer(transfer: StockTransfer, user) -> StockTransfer:
    transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status != TRANSFER_STATUS_DRAFT:
        raise TransferWorkflowError('Chỉ phiếu nháp mới được gửi chuyển.')
    if transfer.from_location_id == transfer.to_location_id:
        raise TransferWorkflowError('Kho gửi và kho nhận phải khác nhau.')
    lines = list(transfer.lines.select_related('material', 'batch'))
    if not lines:
        raise TransferWorkflowError('Phiếu chuyển chưa có dòng chi tiết.')

    for line in lines:
        if line.quantity <= Decimal('0'):
            raise TransferWorkflowError(f'Số lượng chuyển của {line.material.code} phải lớn hơn 0.')
        balance = (
            StockBalance.objects.select_for_update()
            .filter(material=line.material, location=transfer.from_location)
            .first()
        )
        available = balance.quantity if balance else Decimal('0')
        if available < line.quantity:
            raise TransferWorkflowError(
                f'Tồn không đủ tại {transfer.from_location.display_label()}: {line.material.code} '
                f'(có {available}, cần {line.quantity}).'
            )
        balance.quantity -= line.quantity
        balance.save(update_fields=['quantity', 'updated_at'])
        # Chuyển kho không đổi tồn theo lô (lô theo mã NPL); batch chỉ tham chiếu
        unit_price = line.batch.unit_price if line.batch_id else Decimal('0')
        StockLedger.objects.create(
            material=line.material,
            location=transfer.from_location,
            qty_delta=-line.quantity,
            balance_after=balance.quantity,
            batch=line.batch,
            unit_price=unit_price,
            amount=ledger_amount(line.quantity, unit_price),
            ref_type=StockLedger.REF_TRANSFER,
            ref_id=transfer.pk,
            ref_number=transfer.number,
            created_by=user,
            notes=f'Chuyển đi {transfer.number} → {transfer.to_location.display_label()}',
        )

    transfer.status = TRANSFER_STATUS_IN_TRANSIT
    transfer.sent_by = user
    transfer.sent_at = timezone.now()
    transfer.save(update_fields=['status', 'sent_by', 'sent_at'])
    return transfer


@transaction.atomic
def receive_stock_transfer(transfer: StockTransfer, user) -> StockTransfer:
    transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status != TRANSFER_STATUS_IN_TRANSIT:
        raise TransferWorkflowError('Chỉ phiếu đang chuyển mới được nhận vào kho.')

    for line in transfer.lines.select_related('material', 'batch'):
        balance, _ = StockBalance.objects.select_for_update().get_or_create(
            material=line.material,
            location=transfer.to_location,
            defaults={'quantity': Decimal('0')},
        )
        balance.quantity += line.quantity
        balance.save(update_fields=['quantity', 'updated_at'])
        unit_price = line.batch.unit_price if line.batch_id else Decimal('0')
        StockLedger.objects.create(
            material=line.material,
            location=transfer.to_location,
            qty_delta=line.quantity,
            balance_after=balance.quantity,
            batch=line.batch,
            unit_price=unit_price,
            amount=ledger_amount(line.quantity, unit_price),
            ref_type=StockLedger.REF_TRANSFER,
            ref_id=transfer.pk,
            ref_number=transfer.number,
            created_by=user,
            notes=f'Nhận chuyển {transfer.number} từ {transfer.from_location.display_label()}',
        )

    transfer.status = TRANSFER_STATUS_RECEIVED
    transfer.received_by = user
    transfer.received_at = timezone.now()
    transfer.save(update_fields=['status', 'received_by', 'received_at'])
    return transfer


@transaction.atomic
def cancel_stock_transfer(transfer: StockTransfer) -> StockTransfer:
    transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status != TRANSFER_STATUS_DRAFT:
        raise TransferWorkflowError('Chỉ phiếu nháp mới được hủy.')
    transfer.status = TRANSFER_STATUS_CANCELLED
    transfer.save(update_fields=['status'])
    return transfer
