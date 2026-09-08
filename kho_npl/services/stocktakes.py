from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import (
    STOCKTAKE_STATUS_CLOSED,
    STOCKTAKE_STATUS_COUNTING,
    STOCKTAKE_STATUS_DRAFT,
    STOCKTAKE_STATUS_REVIEW,
)
from kho_npl.models import Material, StockBalance, StockLedger, Stocktake, StocktakeLine
from kho_npl.services.batches import (
    BatchWorkflowError,
    apply_variance_to_batches,
    batch_effective_price,
    ledger_amount,
)
from kho_npl.services.uom import UomConversionError, apply_line_conversion


class StocktakeWorkflowError(Exception):
    pass


def stocktake_is_editable(stocktake: Stocktake) -> bool:
    return stocktake.status in (STOCKTAKE_STATUS_DRAFT, STOCKTAKE_STATUS_COUNTING)


def stocktake_attachment_editable_after_close(stocktake: Stocktake) -> bool:
    return stocktake.status in (STOCKTAKE_STATUS_REVIEW, STOCKTAKE_STATUS_CLOSED)


def stocktake_can_count(stocktake: Stocktake) -> bool:
    return stocktake.status in (STOCKTAKE_STATUS_DRAFT, STOCKTAKE_STATUS_COUNTING)


@transaction.atomic
def populate_stocktake_lines(stocktake: Stocktake) -> int:
    if stocktake.status == STOCKTAKE_STATUS_CLOSED:
        raise StocktakeWorkflowError('Kỳ đã chốt — không thể tải lại tồn.')
    if not stocktake.location_id:
        raise StocktakeWorkflowError('Chưa chọn kho kiểm kê.')
    location = stocktake.location
    stocktake.lines.all().delete()
    lines = []
    balances = StockBalance.objects.filter(location=location).select_related('material')
    material_ids = set()
    for balance in balances:
        material_ids.add(balance.material_id)
        lines.append(StocktakeLine(
            stocktake=stocktake,
            material=balance.material,
            location=location,
            system_qty=balance.quantity,
            line_unit=balance.material.unit,
            uom_factor=Decimal('1'),
        ))
    for material in Material.objects.filter(is_active=True).exclude(pk__in=material_ids).order_by('code'):
        lines.append(StocktakeLine(
            stocktake=stocktake,
            material=material,
            location=location,
            system_qty=Decimal('0'),
            line_unit=material.unit,
            uom_factor=Decimal('1'),
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
    for line in stocktake.lines.select_related('material', 'location', 'batch'):
        try:
            actual_base = apply_line_conversion(line, line.actual_qty)
        except UomConversionError as exc:
            raise StocktakeWorkflowError(f'{line.material.code}: {exc}') from exc
        variance = actual_base - line.system_qty
        if variance == 0:
            line.save(update_fields=['line_unit', 'uom_factor', 'qty_base'])
            continue
        try:
            applied = apply_variance_to_batches(
                line.material,
                variance,
                line.batch,
                received_date=stocktake.stocktake_date,
            )
        except BatchWorkflowError as exc:
            raise StocktakeWorkflowError(str(exc)) from exc

        if applied:
            line.batch = applied[0][0]
            line.save(update_fields=['batch', 'line_unit', 'uom_factor', 'qty_base'])
        else:
            line.save(update_fields=['line_unit', 'uom_factor', 'qty_base'])

        balance, _ = StockBalance.objects.select_for_update().get_or_create(
            material=line.material,
            location=line.location,
            defaults={'quantity': Decimal('0')},
        )
        balance.quantity = actual_base
        balance.save(update_fields=['quantity', 'updated_at'])
        running = balance.quantity - variance
        for batch, delta in applied:
            running += delta
            unit_price = batch_effective_price(batch)
            StockLedger.objects.create(
                material=line.material,
                location=line.location,
                qty_delta=delta,
                balance_after=running,
                batch=batch,
                unit_price=unit_price,
                amount=ledger_amount(delta, unit_price),
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
