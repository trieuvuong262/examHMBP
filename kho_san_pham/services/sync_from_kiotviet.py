"""Đồng bộ thành phẩm 1 chiều: kv_product (mirror) → kho_sp_product."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_san_pham.choices import (
    PRODUCT_TYPE_THANH_PHAM,
    SYNC_SOURCE_KIOTVIET,
)
from kho_san_pham.models import Product


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    deactivated: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f'tạo {self.created}',
            f'cập nhật {self.updated}',
            f'bỏ qua {self.skipped}',
        ]
        if self.deactivated:
            parts.append(f'ngừng {self.deactivated}')
        if self.errors:
            parts.append(f'lỗi {len(self.errors)}')
        return ' · '.join(parts)


def _first_image_url(kv) -> str:
    urls = getattr(kv, 'image_urls', None) or []
    for url in urls:
        if url:
            return str(url).strip()
    return ''


def _find_existing(kv) -> Product | None:
    if kv.kiotviet_id is not None:
        found = Product.objects.filter(kiotviet_id=kv.kiotviet_id).first()
        if found:
            return found
    code = (kv.code or '').strip()
    if code:
        found = Product.objects.filter(kiotviet_code__iexact=code).first()
        if found:
            return found
        # SP nhập tay cùng mã KV → gắn liên kết
        found = Product.objects.filter(code__iexact=code, kiotviet_id__isnull=True).first()
        if found:
            return found
    return None


def _apply_kv_fields(product: Product, kv, *, is_new: bool) -> None:
    product.product_type = PRODUCT_TYPE_THANH_PHAM
    product.sync_source = SYNC_SOURCE_KIOTVIET
    product.kiotviet_id = kv.kiotviet_id
    product.kiotviet_code = (kv.code or '').strip()
    product.name = (kv.name or kv.full_name or kv.code or '').strip() or product.kiotviet_code
    product.full_name = (kv.full_name or '').strip()
    product.bar_code = (kv.bar_code or '').strip()
    product.unit = (kv.unit or '').strip()
    product.category_name = (kv.category_name or '').strip()
    product.category_path = (getattr(kv, 'category_path', None) or '').strip()
    product.description = (kv.description or '').strip()
    if kv.base_price is not None:
        product.base_price = Decimal(str(kv.base_price))
    product.allows_sale = kv.allows_sale
    product.is_active = False if kv.is_active is False else True
    product.image_url = _first_image_url(kv)
    product.kv_modified_at = kv.kv_modified_at
    product.synced_at = timezone.now()

    if is_new or not (product.code or '').strip():
        # Quy tắc mã SP chưa chốt — tạm dùng mã KV; user sẽ chỉnh / regenerate sau
        product.code = product.kiotviet_code or f'KV-{kv.kiotviet_id}'


@transaction.atomic
def sync_thanh_pham_from_kiotviet(*, retailer: str | None = None, deactivate_missing: bool = False) -> SyncResult:
    """Đọc mirror KvProduct → upsert Product loại thành phẩm. Không ghi ngược KV."""
    from kiotviet.models import KvProduct
    from kiotviet.sync_service import current_retailer

    result = SyncResult()
    retailer = retailer if retailer is not None else current_retailer()
    if not retailer:
        result.errors.append('KIOTVIET_RETAILER chưa cấu hình.')
        return result

    qs = (
        KvProduct.objects
        .filter(retailer=retailer, is_deleted=False)
        .exclude(code='')
        .order_by('code', 'kiotviet_id')
    )

    seen_ids: set[int] = set()
    for kv in qs.iterator(chunk_size=200):
        try:
            existing = _find_existing(kv)
            if existing and existing.product_type != PRODUCT_TYPE_THANH_PHAM and existing.kiotviet_id is None:
                # Đã là hàng hoá cùng mã — không ghi đè loại; bỏ qua
                result.skipped += 1
                continue

            if existing is None:
                product = Product(code=(kv.code or '').strip() or f'KV-{kv.kiotviet_id}')
                _apply_kv_fields(product, kv, is_new=True)
                # Tránh trùng code nếu đã có hang_hoa cùng mã
                if Product.objects.filter(code__iexact=product.code).exists():
                    product.code = f'KV-{kv.kiotviet_id}'
                product.save()
                result.created += 1
            else:
                _apply_kv_fields(existing, kv, is_new=False)
                existing.save()
                result.updated += 1
                seen_ids.add(existing.pk)
                continue
            seen_ids.add(product.pk)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f'KV#{kv.kiotviet_id} {kv.code}: {exc}'[:200])

    if deactivate_missing:
        stale = (
            Product.objects
            .filter(product_type=PRODUCT_TYPE_THANH_PHAM, sync_source=SYNC_SOURCE_KIOTVIET, is_active=True)
            .exclude(pk__in=seen_ids)
            .exclude(kiotviet_id__isnull=True)
        )
        result.deactivated = stale.update(is_active=False, synced_at=timezone.now())

    return result
