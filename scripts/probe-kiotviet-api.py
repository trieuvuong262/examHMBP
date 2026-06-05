"""Probe KiotViet Public API — list endpoints, totals, incremental params."""
from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django

django.setup()

from kiotviet.client import KiotVietAPIError, KiotVietClient

ENDPOINTS: list[tuple[str, str, dict]] = [
    ('branches', 'branches', {'pageSize': 1, 'currentItem': 0}),
    ('categories', 'categories', {'pageSize': 1, 'currentItem': 0, 'hierachicalData': 'true'}),
    ('products', 'products', {'pageSize': 1, 'currentItem': 0, 'includeInventory': 'false'}),
    ('customers', 'customers', {'pageSize': 1, 'currentItem': 0}),
    ('orders', 'orders', {'pageSize': 1, 'currentItem': 0}),
    ('invoices', 'invoices', {'pageSize': 1, 'currentItem': 0}),
    ('purchase_orders', 'purchaseorders', {'pageSize': 1, 'currentItem': 0}),
    ('product_on_hands', 'productOnHands', {'pageSize': 1, 'currentItem': 0}),
    ('transfers', 'transfers', {'pageSize': 1, 'currentItem': 0}),
    ('returns', 'returns', {'pageSize': 1, 'currentItem': 0}),
    ('cashflow', 'cashflow', {'pageSize': 1, 'currentItem': 0}),
    ('pricebooks', 'pricebooks', {'pageSize': 1, 'currentItem': 0}),
    ('order_suppliers', 'ordersuppliers', {'pageSize': 1, 'currentItem': 0}),
    ('customer_groups', 'customers/group', {'pageSize': 1, 'currentItem': 0}),
    ('users', 'users', {'pageSize': 1, 'currentItem': 0}),
    ('sale_channel', 'salechannel', {'pageSize': 1, 'currentItem': 0}),
    ('bank_accounts', 'BankAccounts', {'pageSize': 1, 'currentItem': 0}),
    ('surcharges', 'surchages', {'pageSize': 1, 'currentItem': 0}),
    ('locations', 'locations', {'pageSize': 1, 'currentItem': 0}),
    ('settings', 'settings', {}),
]

INCREMENTAL_CANDIDATES = [
    ('products', 'products', 'modifiedDate'),
    ('customers', 'customers', 'modifiedDate'),
    ('orders', 'orders', 'modifiedDate'),
    ('invoices', 'invoices', 'modifiedDate'),
    ('purchase_orders', 'purchaseorders', 'modifiedDate'),
    ('transfers', 'transfers', 'modifiedDate'),
    ('returns', 'returns', 'modifiedDate'),
    ('order_suppliers', 'ordersuppliers', 'modifiedDate'),
]


def probe_list(client: KiotVietClient, path: str, params: dict) -> dict:
    clean = {k: v for k, v in params.items() if v not in (None, '')}
    return client._request('GET', path, params=clean)


def main() -> int:
    client = KiotVietClient()
    if not client.is_configured():
        print('KiotViet chưa cấu hình')
        return 1

    print(f'Retailer: {client.retailer}')
    print()
    print(f"{'Entity':<20} {'Status':<8} {'Total':>8}  Ghi chú")
    print('-' * 72)

    synced = {
        'branches', 'categories', 'products', 'customers',
        'orders', 'invoices', 'purchase_orders',
        'transfers', 'returns', 'customer_groups', 'pricebooks',
        'users', 'sale_channel', 'cashflow', 'bank_accounts',
        'surcharges', 'locations',
    }
    partial = {'product_on_hands'}  # inventory via products includeInventory

    for key, path, params in ENDPOINTS:
        try:
            payload = probe_list(client, path, params)
            if key == 'settings':
                total = '—'
                note = 'object' if isinstance(payload, dict) else type(payload).__name__
            else:
                total = int(payload.get('total') or len(payload.get('data') or []) or 0)
                note = ''
                if key in synced:
                    note = 'đã sync'
                elif key in partial:
                    note = 'tồn kho qua products/inventories'
                elif total == 0:
                    note = 'API OK, 0 bản ghi'
            print(f'{key:<20} {"OK":<8} {str(total):>8}  {note}')
        except KiotVietAPIError as exc:
            msg = str(exc)[:60]
            print(f'{key:<20} {"FAIL":<8} {"—":>8}  {msg}')

    print()
    print('Kiểm tra lastModifiedFrom (cursor incremental):')
    print(f"{'Entity':<20} {'lastModifiedFrom':<18} orderBy modifiedDate")
    print('-' * 60)
    cursor = '2020-01-01T00:00:00'
    for key, path, _field in INCREMENTAL_CANDIDATES:
        inc_ok = '—'
        order_ok = '—'
        try:
            probe_list(client, path, {
                'pageSize': 1, 'currentItem': 0, 'lastModifiedFrom': cursor,
            })
            inc_ok = 'OK'
        except KiotVietAPIError as exc:
            inc_ok = f'FAIL: {str(exc)[:35]}'
        try:
            probe_list(client, path, {
                'pageSize': 1, 'currentItem': 0,
                'orderBy': 'modifiedDate', 'orderDirection': 'Desc',
            })
            order_ok = 'OK'
        except KiotVietAPIError as exc:
            order_ok = f'FAIL: {str(exc)[:35]}'
        print(f'{key:<20} {inc_ok:<18} {order_ok}')

    print()
    print('Mẫu field entity có thể bổ sung sync:')
    samples = [
        ('transfers', 'transfers', {'pageSize': 1, 'currentItem': 0}),
        ('returns', 'returns', {'pageSize': 1, 'currentItem': 0}),
        ('pricebooks', 'pricebooks', {'pageSize': 1, 'currentItem': 0}),
        ('customer_groups', 'customers/group', {'pageSize': 1, 'currentItem': 0}),
        ('cashflow', 'cashflow', {'pageSize': 1, 'currentItem': 0}),
        ('order_suppliers', 'ordersuppliers', {'pageSize': 1, 'currentItem': 0}),
    ]
    for key, path, params in samples:
        try:
            payload = probe_list(client, path, params)
            row = (payload.get('data') or [{}])[0]
            if isinstance(row, dict):
                keys = ', '.join(sorted(row.keys())[:16])
                print(f'  {key}: {keys}')
        except KiotVietAPIError as exc:
            print(f'  {key}: FAIL — {exc}')

    print()
    print('Tham số products bổ sung:')
    for label, extra in [
        ('includePricebook', {'includePricebook': 'true'}),
        ('includeMaterial', {'includeMaterial': 'true'}),
    ]:
        try:
            payload = probe_list(client, 'products', {
                'pageSize': 1, 'currentItem': 0, **extra,
            })
            row = (payload.get('data') or [{}])[0]
            keys = sorted(row.keys())[:12]
            print(f'  {label}: OK — sample keys: {", ".join(keys)}...')
        except KiotVietAPIError as exc:
            print(f'  {label}: FAIL — {exc}')

    print()
    print('So sánh mirror DB (portal) vs API total:')
    from kiotviet.models import (
        KvBranch, KvCategory, KvCustomer, KvInvoice, KvOrder,
        KvProduct, KvProductInventory, KvPurchaseOrder,
    )
    retailer = client.retailer
    mirror = {
        'branches': KvBranch.objects.filter(retailer=retailer, is_deleted=False).count(),
        'categories': KvCategory.objects.filter(retailer=retailer, is_deleted=False).count(),
        'products': KvProduct.objects.filter(retailer=retailer, is_deleted=False).count(),
        'customers': KvCustomer.objects.filter(retailer=retailer, is_deleted=False).count(),
        'orders': KvOrder.objects.filter(retailer=retailer, is_deleted=False).count(),
        'invoices': KvInvoice.objects.filter(retailer=retailer, is_deleted=False).count(),
        'purchase_orders': KvPurchaseOrder.objects.filter(retailer=retailer, is_deleted=False).count(),
        'stock_rows': KvProductInventory.objects.filter(retailer=retailer, is_deleted=False).count(),
    }
    api_totals = {}
    for key, path, params in ENDPOINTS[:8]:
        try:
            payload = probe_list(client, path, {**params, 'pageSize': 1})
            api_totals[key] = int(payload.get('total') or 0)
        except KiotVietAPIError:
            api_totals[key] = None
    for key in ('branches', 'categories', 'products', 'customers', 'orders', 'invoices', 'purchase_orders'):
        api_n = api_totals.get(key)
        mir_n = mirror.get(key, 0)
        gap = '' if api_n is None else f' (lệch {api_n - mir_n:+d})' if api_n != mir_n else ''
        print(f'  {key}: mirror={mir_n}, api={api_n}{gap}')
    print(f'  stock_rows (mirror inventory): {mirror["stock_rows"]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
