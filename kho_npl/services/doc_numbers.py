from django.utils import timezone

from kho_npl.models import (
    StockAdjustment,
    StockDisposal,
    StockIssue,
    StockReceipt,
    Stocktake,
    StockTransfer,
)


def _seq_from_number(number: str, base: str) -> int:
    if not number or not number.startswith(base):
        return 0
    try:
        return int(number.rsplit('-', 1)[-1])
    except ValueError:
        return 0


def _max_seq_for_prefix(prefix: str, models, field: str = 'number') -> int:
    year = timezone.localdate().year
    base = f'{prefix}-{year}-'
    max_seq = 0
    for model in models:
        for number in model.objects.filter(**{f'{field}__startswith': base}).values_list(field, flat=True):
            max_seq = max(max_seq, _seq_from_number(number, base))
    return max_seq


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


def _next_kk_number() -> str:
    """Số phiếu kiểm kê KK — dùng chung seq cho StockAdjustment và Stocktake lịch sử."""
    year = timezone.localdate().year
    base = f'KK-{year}-'
    seq = _max_seq_for_prefix('KK', (StockAdjustment, Stocktake)) + 1
    return f'{base}{seq:04d}'


def next_receipt_number() -> str:
    return _next_doc_number('PN', StockReceipt)


def next_issue_number() -> str:
    return _next_doc_number('PX', StockIssue)


def next_adjustment_number() -> str:
    return _next_kk_number()


def next_stocktake_number() -> str:
    return _next_kk_number()


def next_transfer_number() -> str:
    return _next_doc_number('PC', StockTransfer)


def next_disposal_number() -> str:
    return _next_doc_number('PH', StockDisposal)
