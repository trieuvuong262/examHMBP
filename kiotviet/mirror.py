"""Kiểm tra mirror DB trung gian có sẵn để tra cứu."""

from __future__ import annotations

from django.conf import settings

from .models import (
    KvCashflow,
    KvCustomer,
    KvCustomerGroup,
    KvInvoice,
    KvOrder,
    KvPricebook,
    KvProduct,
    KvProductInventory,
    KvPurchaseOrder,
    KvReturn,
    KvSyncState,
    KvTransfer,
    KvUser,
)
from .sync_service import current_retailer

ENTITY_MODELS = {
    'customers': KvCustomer,
    'customer_groups': KvCustomerGroup,
    'products': KvProduct,
    'orders': KvOrder,
    'invoices': KvInvoice,
    'purchase_orders': KvPurchaseOrder,
    'transfers': KvTransfer,
    'returns': KvReturn,
    'cashflow': KvCashflow,
    'pricebooks': KvPricebook,
    'users': KvUser,
    'stock': KvProductInventory,
}


def mirror_enabled() -> bool:
    return bool(getattr(settings, 'KIOTVIET_USE_LOCAL_MIRROR', True))


def entity_count(entity: str, retailer: str | None = None) -> int:
    model = ENTITY_MODELS.get(entity)
    if not model:
        return 0
    retailer = retailer or current_retailer()
    if not retailer:
        return 0
    qs = model.objects.filter(retailer=retailer, is_deleted=False)
    return qs.count()


def use_local_mirror(entity: str, retailer: str | None = None) -> bool:
    """Portal tra cứu luôn đọc mirror kv_* (không gọi API trực tiếp)."""
    if not mirror_enabled():
        return False
    retailer = retailer or current_retailer()
    return bool(retailer)


def portal_mirror_ready(retailer: str | None = None) -> bool:
    """Mirror bật + đã cấu hình retailer (dù chưa sync dữ liệu)."""
    return use_local_mirror('customers', retailer=retailer)


def mirror_summary(retailer: str | None = None) -> dict[str, int]:
    retailer = retailer or current_retailer()
    return {name: entity_count(name, retailer) for name in ENTITY_MODELS}


def sync_states(retailer: str | None = None) -> list[KvSyncState]:
    retailer = retailer or current_retailer()
    if not retailer:
        return []
    return list(KvSyncState.objects.filter(retailer=retailer).order_by('entity_type'))
