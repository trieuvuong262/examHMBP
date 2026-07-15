from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_CANCELLED, DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.models import StockBalance, StockDisposal, StockLedger
from kho_npl.services.batches import (
    BatchWorkflowError,
    batch_effective_price,
    decrease_batch_qty,
    ledger_amount,
    validate_batch_for_material,
)
from kho_npl.services.scrap_warehouse import get_scrap_location


class DisposalWorkflowError(Exception):
    pass


def disposal_is_editable(disposal: StockDisposal) -> bool:
    return disposal.status == DOC_STATUS_DRAFT


@transaction.atomic
def post_stock_disposal(disposal: StockDisposal, user) -> StockDisposal:
    disposal = StockDisposal.objects.select_for_update().get(pk=disposal.pk)
    if disposal.status != DOC_STATUS_DRAFT:
        raise DisposalWorkflowError('Chỉ phiếu nháp mới được ghi sổ.')

    scrap_location = get_scrap_location()
    lines = list(disposal.lines.select_related('material', 'location', 'batch'))
    if not lines:
        raise DisposalWorkflowError('Phiếu hủy chưa có dòng chi tiết.')

    for line in lines:
        if line.quantity <= Decimal('0'):
            raise DisposalWorkflowError(f'Số lượng hủy của {line.material.code} phải lớn hơn 0.')
        if not line.location_id:
            raise DisposalWorkflowError(f'Dòng {line.material.code} chưa chọn vị trí kho.')
        if line.location_id == scrap_location.pk:
            raise DisposalWorkflowError('Vị trí nguồn không được là kho hủy.')

        try:
            batch = validate_batch_for_material(line.batch, line.material)
            decrease_batch_qty(batch, line.quantity, material_code=line.material.code)
        except BatchWorkflowError as exc:
            raise DisposalWorkflowError(str(exc)) from exc

        source_balance = (
            StockBalance.objects.select_for_update()
            .filter(material=line.material, location=line.location)
            .first()
        )
        available = source_balance.quantity if source_balance else Decimal('0')
        if available < line.quantity:
            raise DisposalWorkflowError(
                f'Tồn không đủ tại {line.location.display_label()}: {line.material.code} '
                f'(có {available}, cần hủy {line.quantity}).'
            )
        source_balance.quantity -= line.quantity
        source_balance.save(update_fields=['quantity', 'updated_at'])
        StockLedger.objects.create(
            material=line.material,
            location=line.location,
            qty_delta=-line.quantity,
            balance_after=source_balance.quantity,
            batch=batch,
            unit_price=batch_effective_price(batch),
            amount=ledger_amount(line.quantity, batch_effective_price(batch)),
            ref_type=StockLedger.REF_DISPOSAL,
            ref_id=disposal.pk,
            ref_number=disposal.number,
            created_by=user,
            notes=f'Hủy {disposal.number} → {scrap_location.display_label()}',
        )

        scrap_balance, _ = StockBalance.objects.select_for_update().get_or_create(
            material=line.material,
            location=scrap_location,
            defaults={'quantity': Decimal('0')},
        )
        scrap_balance.quantity += line.quantity
        scrap_balance.save(update_fields=['quantity', 'updated_at'])
        StockLedger.objects.create(
            material=line.material,
            location=scrap_location,
            qty_delta=line.quantity,
            balance_after=scrap_balance.quantity,
            batch=batch,
            unit_price=batch_effective_price(batch),
            amount=ledger_amount(line.quantity, batch_effective_price(batch)),
            ref_type=StockLedger.REF_DISPOSAL,
            ref_id=disposal.pk,
            ref_number=disposal.number,
            created_by=user,
            notes=f'Nhận hủy {disposal.number} từ {line.location.display_label()}',
        )

    disposal.status = DOC_STATUS_POSTED
    disposal.posted_by = user
    disposal.posted_at = timezone.now()
    disposal.save(update_fields=['status', 'posted_by', 'posted_at'])
    return disposal


@transaction.atomic
def cancel_stock_disposal(disposal: StockDisposal) -> StockDisposal:
    disposal = StockDisposal.objects.select_for_update().get(pk=disposal.pk)
    if disposal.status != DOC_STATUS_DRAFT:
        raise DisposalWorkflowError('Chỉ phiếu nháp mới được hủy.')
    disposal.status = DOC_STATUS_CANCELLED
    disposal.save(update_fields=['status'])
    return disposal
