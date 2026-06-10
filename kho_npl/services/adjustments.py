from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import ADJUST_STATUS_APPROVED, ADJUST_STATUS_PENDING, ADJUST_STATUS_REJECTED
from kho_npl.models import StockAdjustment, StockBalance, StockLedger


class AdjustmentWorkflowError(Exception):
    pass


def balance_qty(material, location) -> Decimal:
    balance = StockBalance.objects.filter(material=material, location=location).first()
    return balance.quantity if balance else Decimal('0')


def adjustment_is_editable(adjustment: StockAdjustment) -> bool:
    return adjustment.status == ADJUST_STATUS_PENDING


@transaction.atomic
def approve_stock_adjustment(adjustment: StockAdjustment, user) -> StockAdjustment:
    adjustment = StockAdjustment.objects.select_for_update().get(pk=adjustment.pk)
    if adjustment.status != ADJUST_STATUS_PENDING:
        raise AdjustmentWorkflowError('Chỉ phiếu chờ duyệt mới được phê duyệt.')
    variance = adjustment.actual_qty - adjustment.system_qty
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        material=adjustment.material,
        location=adjustment.location,
        defaults={'quantity': Decimal('0')},
    )
    balance.quantity = adjustment.actual_qty
    balance.save(update_fields=['quantity', 'updated_at'])
    if variance != 0:
        StockLedger.objects.create(
            material=adjustment.material,
            location=adjustment.location,
            qty_delta=variance,
            balance_after=balance.quantity,
            ref_type=StockLedger.REF_ADJUSTMENT,
            ref_id=adjustment.pk,
            ref_number=adjustment.number,
            created_by=user,
            notes=adjustment.reason[:255],
        )
    adjustment.status = ADJUST_STATUS_APPROVED
    adjustment.approved_by = user
    adjustment.approved_at = timezone.now()
    adjustment.save(update_fields=['status', 'approved_by', 'approved_at'])
    return adjustment


@transaction.atomic
def reject_stock_adjustment(adjustment: StockAdjustment, user) -> StockAdjustment:
    adjustment = StockAdjustment.objects.select_for_update().get(pk=adjustment.pk)
    if adjustment.status != ADJUST_STATUS_PENDING:
        raise AdjustmentWorkflowError('Chỉ phiếu chờ duyệt mới được từ chối.')
    adjustment.status = ADJUST_STATUS_REJECTED
    adjustment.approved_by = user
    adjustment.approved_at = timezone.now()
    adjustment.save(update_fields=['status', 'approved_by', 'approved_at'])
    return adjustment
