"""Cầu nối một chiều KiotViet mirror → Odoo.

Giai đoạn 1 — ĐỐI CHIẾU (chỉ đọc, KHÔNG ghi gì lên Odoo).

So khớp sản phẩm giữa mirror ``kv_product`` và Odoo theo khóa:
    KvProduct.code  ==  Odoo product.product.default_code

Kết quả phân loại để biết trước khi migrate:
    - matched          : mã khớp đúng 1 SP trên Odoo
    - missing_in_odoo  : có ở KiotViet, chưa có trên Odoo (cần tạo)
    - price_mismatch   : khớp mã nhưng lệch giá bán
    - name_mismatch    : khớp mã nhưng lệch tên
    - duplicate_in_kv  : cùng 1 mã xuất hiện nhiều lần trong kv_product
    - duplicate_in_odoo: 1 mã ứng với nhiều SP trên Odoo (dữ liệu Odoo bẩn)
    - no_code          : SP KiotViet thiếu mã (không thể đối chiếu)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from audit.services.odoo_sync import _execute, odoo_configured
from kiotviet.models import KvProduct
from kiotviet.sync_service import current_retailer

logger = logging.getLogger(__name__)

PRICE_TOLERANCE = Decimal('0.01')
_ODOO_READ_BATCH = 400
_ODOO_FIELDS = ['id', 'default_code', 'barcode', 'name', 'list_price', 'active', 'type']


def odoo_ready() -> bool:
    """True khi Odoo XML-RPC đã cấu hình đủ (ODOO_URL/DB/API_USER/PASSWORD)."""
    return odoo_configured()


def _norm_code(value) -> str:
    return (str(value).strip() if value else '')


def _to_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def fetch_odoo_products_by_code(codes) -> dict[str, list[dict]]:
    """Đọc SP Odoo theo danh sách default_code. Chỉ đọc, gồm cả SP inactive.

    Trả về dict: code -> list[record]. Có thể >1 record nếu Odoo trùng mã.
    """
    result: dict[str, list[dict]] = {}
    unique_codes = [c for c in {_norm_code(c) for c in codes} if c]
    if not unique_codes:
        return result

    for i in range(0, len(unique_codes), _ODOO_READ_BATCH):
        chunk = unique_codes[i:i + _ODOO_READ_BATCH]
        records = _execute(
            'product.product',
            'search_read',
            [['default_code', 'in', chunk]],
            fields=_ODOO_FIELDS,
            context={'active_test': False},
        )
        for rec in records or []:
            key = _norm_code(rec.get('default_code'))
            if key:
                result.setdefault(key, []).append(rec)
    return result


@dataclass
class ReconResult:
    retailer: str = ''
    kv_total: int = 0
    odoo_matched_codes: int = 0
    matched: list = field(default_factory=list)
    missing_in_odoo: list = field(default_factory=list)
    price_mismatch: list = field(default_factory=list)
    name_mismatch: list = field(default_factory=list)
    duplicate_in_kv: list = field(default_factory=list)
    duplicate_in_odoo: list = field(default_factory=list)
    no_code: list = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            'kv_total': self.kv_total,
            'matched': len(self.matched),
            'missing_in_odoo': len(self.missing_in_odoo),
            'price_mismatch': len(self.price_mismatch),
            'name_mismatch': len(self.name_mismatch),
            'duplicate_in_kv': len(self.duplicate_in_kv),
            'duplicate_in_odoo': len(self.duplicate_in_odoo),
            'no_code': len(self.no_code),
        }


def _kv_products(retailer: str):
    qs = KvProduct.objects.filter(is_deleted=False)
    if retailer:
        qs = qs.filter(retailer=retailer)
    # Bỏ SP đã ngừng kinh doanh; giữ is_active True hoặc chưa xác định (None).
    return qs.exclude(is_active=False).order_by('code', 'kiotviet_id')


def reconcile_products(retailer: str | None = None) -> ReconResult:
    """So khớp kv_product ↔ Odoo theo code=default_code. Chỉ đọc."""
    retailer = retailer if retailer is not None else current_retailer()
    result = ReconResult(retailer=retailer)

    products = list(_kv_products(retailer))
    result.kv_total = len(products)
    if not products:
        return result

    # Gom theo mã để phát hiện trùng mã trong chính KiotViet.
    by_code: dict[str, list[KvProduct]] = {}
    for prod in products:
        code = _norm_code(prod.code)
        if not code:
            result.no_code.append({
                'kiotviet_id': prod.kiotviet_id,
                'name': prod.name,
                'bar_code': prod.bar_code,
            })
            continue
        by_code.setdefault(code, []).append(prod)

    odoo_by_code = fetch_odoo_products_by_code(by_code.keys())
    result.odoo_matched_codes = len(odoo_by_code)

    for code, kv_group in by_code.items():
        if len(kv_group) > 1:
            result.duplicate_in_kv.append({
                'code': code,
                'count': len(kv_group),
                'kiotviet_ids': [p.kiotviet_id for p in kv_group],
                'names': [p.name for p in kv_group],
            })

        kv = kv_group[0]
        odoo_records = odoo_by_code.get(code)

        if not odoo_records:
            result.missing_in_odoo.append({
                'code': code,
                'kiotviet_id': kv.kiotviet_id,
                'name': kv.name,
                'bar_code': kv.bar_code,
                'base_price': str(kv.base_price) if kv.base_price is not None else '',
                'category_path': kv.category_path,
            })
            continue

        if len(odoo_records) > 1:
            result.duplicate_in_odoo.append({
                'code': code,
                'count': len(odoo_records),
                'odoo_ids': [r.get('id') for r in odoo_records],
            })

        odoo = odoo_records[0]
        result.matched.append({
            'code': code,
            'kiotviet_id': kv.kiotviet_id,
            'odoo_id': odoo.get('id'),
            'kv_name': kv.name,
            'odoo_name': odoo.get('name'),
        })

        kv_price = _to_decimal(kv.base_price)
        odoo_price = _to_decimal(odoo.get('list_price'))
        if kv_price is not None and odoo_price is not None:
            if abs(kv_price - odoo_price) > PRICE_TOLERANCE:
                result.price_mismatch.append({
                    'code': code,
                    'kiotviet_id': kv.kiotviet_id,
                    'odoo_id': odoo.get('id'),
                    'kv_price': str(kv_price),
                    'odoo_price': str(odoo_price),
                })

        kv_name = (kv.name or '').strip()
        odoo_name = (odoo.get('name') or '').strip()
        if kv_name and odoo_name and kv_name.lower() != odoo_name.lower():
            result.name_mismatch.append({
                'code': code,
                'kiotviet_id': kv.kiotviet_id,
                'odoo_id': odoo.get('id'),
                'kv_name': kv_name,
                'odoo_name': odoo_name,
            })

    return result
