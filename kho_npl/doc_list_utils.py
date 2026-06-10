"""Tiện ích lọc/sắp xếp danh sách phiếu kho NPL."""

from kho_npl.choices import (
    DOC_STATUS_CANCELLED,
    DOC_STATUS_DRAFT,
    DOC_STATUS_LABELS,
    DOC_STATUS_POSTED,
    STOCKTAKE_STATUS_CLOSED,
    STOCKTAKE_STATUS_COUNTING,
    STOCKTAKE_STATUS_DRAFT,
    STOCKTAKE_STATUS_LABELS,
    STOCKTAKE_STATUS_REVIEW,
)

DOC_STATUS_FILTER_CHOICES = (
    ('', 'Tất cả'),
    (DOC_STATUS_DRAFT, DOC_STATUS_LABELS[DOC_STATUS_DRAFT]),
    (DOC_STATUS_POSTED, DOC_STATUS_LABELS[DOC_STATUS_POSTED]),
    (DOC_STATUS_CANCELLED, DOC_STATUS_LABELS[DOC_STATUS_CANCELLED]),
)

STOCKTAKE_STATUS_FILTER_CHOICES = (
    ('', 'Tất cả'),
    (STOCKTAKE_STATUS_DRAFT, STOCKTAKE_STATUS_LABELS[STOCKTAKE_STATUS_DRAFT]),
    (STOCKTAKE_STATUS_COUNTING, STOCKTAKE_STATUS_LABELS[STOCKTAKE_STATUS_COUNTING]),
    (STOCKTAKE_STATUS_REVIEW, STOCKTAKE_STATUS_LABELS[STOCKTAKE_STATUS_REVIEW]),
    (STOCKTAKE_STATUS_CLOSED, STOCKTAKE_STATUS_LABELS[STOCKTAKE_STATUS_CLOSED]),
)


def doc_status_filter(request, *, choices: tuple) -> str:
    valid = {value for value, _ in choices}
    status = (request.GET.get('status') or '').strip().lower()
    if status not in valid:
        return ''
    return status


def doc_list_sort(
    request,
    sort_fields: dict,
    *,
    default_key: str = 'number',
    default_dir: str = 'desc',
):
    sort_key = (request.GET.get('sort') or default_key).strip()
    sort_dir = (request.GET.get('dir') or default_dir).strip().lower()
    if sort_key not in sort_fields:
        sort_key = default_key
    if sort_dir not in ('asc', 'desc'):
        sort_dir = default_dir
    orm_field = sort_fields[sort_key]
    order = orm_field if sort_dir == 'asc' else f'-{orm_field}'
    return sort_key, sort_dir, order
