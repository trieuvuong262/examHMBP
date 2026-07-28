"""Sinh mã vạch nội bộ dạng EAN-13 (tiền tố 20 = mã cửa hàng)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import transaction

from kho_san_pham.models import Product

# EAN-13 nội bộ cửa hàng (đầu 2…) — không cần mã GS1
BARCODE_PREFIX = '20'
_BARCODE_BODY_RE = re.compile(rf'^{BARCODE_PREFIX}(\d{{10}})\d$')


def ean13_check_digit(body12: str) -> str:
    if len(body12) != 12 or not body12.isdigit():
        raise ValueError('EAN-13 cần đúng 12 chữ số trước check digit.')
    total = 0
    for i, ch in enumerate(body12):
        total += int(ch) if i % 2 == 0 else int(ch) * 3
    return str((10 - (total % 10)) % 10)


def build_ean13(sequence: int) -> str:
    if sequence < 1 or sequence > 9_999_999_999:
        raise ValueError('STT mã vạch ngoài phạm vi.')
    body = f'{BARCODE_PREFIX}{sequence:010d}'
    return body + ean13_check_digit(body)


def _sequence_from_barcode(code: str) -> int | None:
    m = _BARCODE_BODY_RE.match((code or '').strip())
    if not m:
        return None
    return int(m.group(1))


def next_barcode_sequence() -> int:
    current = 0
    for code in Product.objects.exclude(bar_code='').values_list('bar_code', flat=True).iterator():
        seq = _sequence_from_barcode(code)
        if seq and seq > current:
            current = seq
    return current + 1


def allocate_barcode(*, used: set[str] | None = None) -> str:
    """Sinh một mã vạch chưa trùng (trong DB + tập ``used`` tạm)."""
    used = used if used is not None else set()
    seq = next_barcode_sequence()
    while True:
        code = build_ean13(seq)
        if code not in used and not Product.objects.filter(bar_code=code).exists():
            used.add(code)
            return code
        seq += 1


@dataclass
class BarcodeAssignResult:
    updated: int = 0
    skipped: int = 0


@transaction.atomic
def assign_barcodes_to_all_products(*, force: bool = True) -> BarcodeAssignResult:
    """Gán mã vạch EAN-13 cho SP.

    ``force=True``: tạo mới cho mọi SP (kể cả đã có).
    ``force=False``: chỉ SP đang trống mã vạch.
    """
    result = BarcodeAssignResult()
    if force:
        products = list(Product.objects.order_by('pk').only('pk', 'bar_code'))
        seq = 1
    else:
        products = list(Product.objects.filter(bar_code='').order_by('pk').only('pk', 'bar_code'))
        seq = next_barcode_sequence()

    if not products:
        return result

    to_update: list[Product] = []
    for product in products:
        code = build_ean13(seq)
        seq += 1
        if (product.bar_code or '') == code:
            result.skipped += 1
            continue
        product.bar_code = code
        to_update.append(product)
        result.updated += 1

    if to_update:
        Product.objects.bulk_update(to_update, ['bar_code'], batch_size=500)
    return result
