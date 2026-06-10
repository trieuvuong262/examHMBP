from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import (
    STOCKTAKE_STATUS_CLOSED,
    STOCKTAKE_STATUS_COUNTING,
    STOCKTAKE_STATUS_DRAFT,
)
from kho_npl.models import Material, StockBalance, StockLedger, Stocktake, StocktakeLine


class StocktakeWorkflowError(Exception):
    pass


def stocktake_is_editable(stocktake: Stocktake) -> bool:
    return stocktake.status in (STOCKTAKE_STATUS_DRAFT, STOCKTAKE_STATUS_COUNTING)


def stocktake_can_count(stocktake: Stocktake) -> bool:
    return stocktake.status in (STOCKTAKE_STATUS_DRAFT, STOCKTAKE_STATUS_COUNTING)


@transaction.atomic
def populate_stocktake_lines(stocktake: Stocktake) -> int:
    if stocktake.status == STOCKTAKE_STATUS_CLOSED:
        raise StocktakeWorkflowError('Kỳ đã chốt — không thể tải lại tồn.')
    stocktake.lines.all().delete()
    lines = []
    for balance in StockBalance.objects.select_related('material', 'location').all():
        lines.append(StocktakeLine(
            stocktake=stocktake,
            material=balance.material,
            location=balance.location,
            system_qty=balance.quantity,
        ))
    if not lines:
        from kho_npl.models import WarehouseLocation
        main_location = WarehouseLocation.objects.filter(code='MAIN', is_active=True).first()
        if main_location:
            for material in Material.objects.filter(is_active=True):
                lines.append(StocktakeLine(
                    stocktake=stocktake,
                    material=material,
                    location=main_location,
                    system_qty=Decimal('0'),
                ))
    StocktakeLine.objects.bulk_create(lines)
    return len(lines)


@transaction.atomic
def start_stocktake_counting(stocktake: Stocktake) -> Stocktake:
    stocktake = Stocktake.objects.select_for_update().get(pk=stocktake.pk)
    if stocktake.status == STOCKTAKE_STATUS_CLOSED:
        raise StocktakeWorkflowError('Kỳ đã chốt.')
    if not stocktake.lines.exists():
        populate_stocktake_lines(stocktake)
    stocktake.status = STOCKTAKE_STATUS_COUNTING
    stocktake.save(update_fields=['status'])
    return stocktake


@transaction.atomic
def close_stocktake(stocktake: Stocktake, user) -> Stocktake:
    stocktake = Stocktake.objects.select_for_update().get(pk=stocktake.pk)
    if stocktake.status == STOCKTAKE_STATUS_CLOSED:
        raise StocktakeWorkflowError('Kỳ đã chốt.')
    if not stocktake.lines.exists():
        raise StocktakeWorkflowError('Chưa có dòng kiểm kê.')
    uncounted = stocktake.lines.filter(actual_qty__isnull=True).count()
    if uncounted:
        raise StocktakeWorkflowError(f'Còn {uncounted} dòng chưa nhập tồn thực tế.')
    for line in stocktake.lines.select_related('material', 'location'):
        variance = line.actual_qty - line.system_qty
        if variance == 0:
            continue
        balance, _ = StockBalance.objects.select_for_update().get_or_create(
            material=line.material,
            location=line.location,
            defaults={'quantity': Decimal('0')},
        )
        balance.quantity = line.actual_qty
        balance.save(update_fields=['quantity', 'updated_at'])
        StockLedger.objects.create(
            material=line.material,
            location=line.location,
            qty_delta=variance,
            balance_after=balance.quantity,
            ref_type=StockLedger.REF_STOCKTAKE,
            ref_id=stocktake.pk,
            ref_number=stocktake.number,
            created_by=user,
            notes=f'Kiểm kê {stocktake.number}',
        )
    stocktake.status = STOCKTAKE_STATUS_CLOSED
    stocktake.closed_at = timezone.now()
    stocktake.save(update_fields=['status', 'closed_at'])
    return stocktake
