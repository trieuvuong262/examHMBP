"""So sánh mirror vs API totals trên VPS."""
from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django

django.setup()

from kiotviet.client import KiotVietClient
from kiotviet.models import (
    KvBranch,
    KvCategory,
    KvCustomer,
    KvInvoice,
    KvOrder,
    KvProduct,
    KvPurchaseOrder,
    KvReturn,
    KvSyncState,
)
from kiotviet.sync_service import ENTITY_ALL, MODEL_BY_ENTITY, current_retailer


def api_total(client: KiotVietClient, path: str, **params) -> int | None:
    try:
        payload = client._request('GET', path, params={**params, 'pageSize': 1, 'currentItem': 0})
        return int(payload.get('total') or 0)
    except Exception:
        return None


def main() -> int:
    retailer = current_retailer()
    client = KiotVietClient()
    api_map = {
        'branches': ('branches', {}),
        'categories': ('categories', {'hierachicalData': 'true'}),
        'products': ('products', {'includeInventory': 'false'}),
        'customers': ('customers', {}),
        'orders': ('orders', {}),
        'invoices': ('invoices', {}),
        'purchase_orders': ('purchaseorders', {}),
        'transfers': ('transfers', {}),
        'returns': ('returns', {}),
    }
    print(f'Retailer: {retailer}')
    print(f'ENTITY_ALL: {len(ENTITY_ALL)} entity')
    print()
    print('Entity có thể CẬP NHẬT (mirror < API):')
    gaps = []
    for entity, model in MODEL_BY_ENTITY.items():
        mir = model.objects.filter(retailer=retailer, is_deleted=False).count()
        if entity in api_map:
            path, params = api_map[entity]
            api_n = api_total(client, path, **params)
            if api_n is not None and api_n > mir:
                gaps.append((entity, mir, api_n, api_n - mir))
    if not gaps:
        print('  (không có trong các entity so sánh trực tiếp)')
    for entity, mir, api_n, diff in sorted(gaps, key=lambda x: -x[3]):
        print(f'  {entity}: mirror={mir}, api={api_n}, thiếu {diff}')

    print()
    print('Returns chi tiết:')
    r = KvReturn.objects.filter(retailer=retailer)
    print(f'  active={r.filter(is_deleted=False).count()}, deleted={r.filter(is_deleted=True).count()}, all={r.count()}')

    print()
    print('Products ảnh:')
    p = KvProduct.objects.filter(retailer=retailer, is_deleted=False)
    print(f'  có image_urls={p.exclude(image_urls=[]).count()}/{p.count()}')

    print()
    print('Sync state có lỗi:')
    errs = KvSyncState.objects.filter(retailer=retailer).exclude(last_error='')
    if not errs:
        print('  không')
    for st in errs:
        print(f'  {st.entity_type}: {st.last_error[:100]}')

    print()
    print('Chưa có trong ENTITY_ALL (API có):')
    print('  order_suppliers — tắt trên KiotViet')
    print('  kv_product_pricebook — includePricebook trên /products')
    print('  kv_customer_group_member — nested customerGroupDetails')
    print('  settings, webhooks — cấu hình, không mirror')
    return 0


if __name__ == '__main__':
    sys.exit(main())
