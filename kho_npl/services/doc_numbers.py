from django.utils import timezone

from kho_npl.models import (
    StockAdjustment,
    StockIssue,
    StockReceipt,
    Stocktake,
)


def _next_doc_number(prefix: str, model, field: str = 'number') -> str:
    year = timezone.localdate().year
    base = f'{prefix}-{year}-'
    latest = (
        model.objects.filter(**{f'{field}__startswith': base})
        .order_by('-id')
        .values_list(field, flat=True)
        .first()
    )
    if not latest:
        return f'{base}0001'
    try:
        seq = int(latest.rsplit('-', 1)[-1]) + 1
    except ValueError:
        seq = model.objects.filter(**{f'{field}__startswith': base}).count() + 1
    return f'{base}{seq:04d}'


def next_receipt_number() -> str:
    return _next_doc_number('PN', StockReceipt)


def next_issue_number() -> str:
    return _next_doc_number('PX', StockIssue)


def next_adjustment_number() -> str:
    return _next_doc_number('DC', StockAdjustment)


def next_stocktake_number() -> str:
    return _next_doc_number('KK', Stocktake)
