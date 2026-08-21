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
    resolve_outflow_batches,
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

        try:
            allocations = resolve_outflow_batches(line.material, line.quantity, line.batch)
        except BatchWorkflowError as exc:
            raise DisposalWorkflowError(str(exc)) from exc

        primary_batch = allocations[0][0]
        line.batch = primary_batch
        line.save(update_fields=['batch'])

        running_source = source_balance.quantity
        scrap_balance, _ = StockBalance.objects.select_for_update().get_or_create(
            material=line.material,
            location=scrap_location,
            defaults={'quantity': Decimal('0')},
        )
        running_scrap = scrap_balance.quantity

        for batch, take in allocations:
            try:
                decrease_batch_qty(batch, take, material_code=line.material.code)
            except BatchWorkflowError as exc:
                raise DisposalWorkflowError(str(exc)) from exc
            unit_price = batch_effective_price(batch)
            running_source -= take
            StockLedger.objects.create(
                material=line.material,
                location=line.location,
                qty_delta=-take,
                balance_after=running_source,
                batch=batch,
                unit_price=unit_price,
                amount=ledger_amount(take, unit_price),
                ref_type=StockLedger.REF_DISPOSAL,
                ref_id=disposal.pk,
                ref_number=disposal.number,
                created_by=user,
                notes=f'Hủy {disposal.number} → {scrap_location.display_label()}',
            )
            running_scrap += take
            StockLedger.objects.create(
                material=line.material,
                location=scrap_location,
                qty_delta=take,
                balance_after=running_scrap,
                batch=batch,
                unit_price=unit_price,
                amount=ledger_amount(take, unit_price),
                ref_type=StockLedger.REF_DISPOSAL,
                ref_id=disposal.pk,
                ref_number=disposal.number,
                created_by=user,
                notes=f'Nhận hủy {disposal.number} từ {line.location.display_label()}',
            )

        source_balance.quantity = running_source
        source_balance.save(update_fields=['quantity', 'updated_at'])
        scrap_balance.quantity = running_scrap
        scrap_balance.save(update_fields=['quantity', 'updated_at'])

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
