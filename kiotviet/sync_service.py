"""Đồng bộ dữ liệu KiotViet API → bảng kv_* trên PostgreSQL portal."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .client import KiotVietAPIError, KiotVietClient
from .kv_parse import (
    parse_kv_date,
    parse_kv_datetime,
    parse_kv_decimal,
    parse_kv_float,
    parse_kv_int,
)
from .sync_helpers import extract_product_image_urls, needs_upsert
from .models import (
    KvBranch,
    KvCategory,
    KvCustomer,
    KvInvoice,
    KvInvoiceLine,
    KvOrder,
    KvOrderLine,
    KvProduct,
    KvProductAttribute,
    KvProductInventory,
    KvProductUnit,
    KvPurchaseOrder,
    KvPurchaseOrderLine,
    KvSyncState,
    KvSyncTombstone,
)

logger = logging.getLogger(__name__)

ENTITY_ALL = (
    'branches',
    'categories',
    'products',
    'customers',
    'orders',
    'invoices',
    'purchase_orders',
)

ENTITY_LABELS = {
    'branches': 'Chi nhánh',
    'categories': 'Nhóm hàng',
    'products': 'Sản phẩm',
    'customers': 'Khách hàng',
    'orders': 'Đặt hàng',
    'invoices': 'Hóa đơn',
    'purchase_orders': 'Đơn nhập hàng',
}

ProgressCallback = Callable[[int, int, str], None]

MODEL_BY_ENTITY = {
    'branches': KvBranch,
    'categories': KvCategory,
    'products': KvProduct,
    'customers': KvCustomer,
    'orders': KvOrder,
    'invoices': KvInvoice,
    'purchase_orders': KvPurchaseOrder,
}


def sync_page_size() -> int:
    return max(10, int(getattr(settings, 'KIOTVIET_SYNC_PAGE_SIZE', 100) or 100))


def current_retailer() -> str:
    return (getattr(settings, 'KIOTVIET_RETAILER', '') or '').strip()


def _format_modified_cursor(dt: datetime) -> str:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.isoformat()


def _handle_removed_ids(entity_type: str, retailer: str, removed_ids: list) -> int:
    model = MODEL_BY_ENTITY.get(entity_type)
    if not model or not removed_ids:
        return 0
    count = 0
    for raw_id in removed_ids:
        try:
            kid = int(raw_id)
        except (TypeError, ValueError):
            continue
        KvSyncTombstone.objects.get_or_create(
            entity_type=entity_type,
            kiotviet_id=kid,
            retailer=retailer,
        )
        updated = model.objects.filter(retailer=retailer, kiotviet_id=kid).update(is_deleted=True)
        if updated:
            count += 1
    return count


def _track_max_modified(row: dict, current: datetime | None) -> datetime | None:
    md = parse_kv_datetime(row.get('modifiedDate'))
    if md and (current is None or md > current):
        return md
    return current


def _sync_paginated(
    *,
    entity_type: str,
    retailer: str,
    list_fn: Callable[..., dict],
    upsert_fn: Callable[[str, dict], bool],
    base_params: dict[str, Any] | None = None,
    full: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    state, _ = KvSyncState.objects.get_or_create(entity_type=entity_type, retailer=retailer)
    page_size = sync_page_size()
    params: dict[str, Any] = dict(base_params or {})
    params['pageSize'] = page_size
    params['includeRemoveIds'] = 'true'
    if not full and state.last_modified_from:
        params['lastModifiedFrom'] = _format_modified_cursor(state.last_modified_from)

    current_item = 0
    max_modified = state.last_modified_from
    rows_total = 0
    upserted_total = 0
    skipped_total = 0
    removed_total = 0
    pages = 0

    try:
        while True:
            params['currentItem'] = current_item
            payload = list_fn(**params)
            rows = payload.get('data') or []
            removed_total += _handle_removed_ids(
                entity_type,
                retailer,
                payload.get('removedIds') or [],
            )
            for row in rows:
                if upsert_fn(retailer, row):
                    upserted_total += 1
                else:
                    skipped_total += 1
                max_modified = _track_max_modified(row, max_modified)
                rows_total += 1

            api_total = int(payload.get('total') or 0)
            pages += 1
            if on_progress:
                on_progress(current_item, api_total, entity_type)
            if not rows:
                break
            current_item += len(rows)
            if on_progress:
                on_progress(current_item, api_total, entity_type)
            if api_total and current_item >= api_total:
                break
            if len(rows) < page_size:
                break

        model = MODEL_BY_ENTITY.get(entity_type)
        record_count = 0
        if model:
            record_count = model.objects.filter(retailer=retailer, is_deleted=False).count()

        state.last_success_at = timezone.now()
        state.records_total = record_count
        state.last_error = ''
        if max_modified:
            state.last_modified_from = max_modified
        if full:
            state.last_full_sync_at = timezone.now()
        state.save()

        return {
            'entity': entity_type,
            'rows': rows_total,
            'upserted': upserted_total,
            'skipped': skipped_total,
            'removed': removed_total,
            'pages': pages,
            'records': record_count,
            'error': None,
        }
    except KiotVietAPIError as exc:
        state.last_error = str(exc)[:2000]
        state.save(update_fields=['last_error'])
        logger.exception('KiotViet sync %s failed', entity_type)
        return {
            'entity': entity_type,
            'rows': rows_total,
            'upserted': upserted_total,
            'skipped': skipped_total,
            'removed': removed_total,
            'pages': pages,
            'records': state.records_total,
            'error': str(exc),
        }


def upsert_branch(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(KvBranch, retailer=retailer, kiotviet_id=kid, incoming_modified=modified):
        return False
    KvBranch.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'branch_name': row.get('branchName') or '',
            'branch_code': row.get('branchCode') or '',
            'contact_number': row.get('contactNumber') or '',
            'email': row.get('email') or '',
            'address': row.get('address') or '',
            'kv_created_at': parse_kv_datetime(row.get('createdDate')),
            'kv_modified_at': parse_kv_datetime(row.get('modifiedDate')),
            'is_deleted': False,
        },
    )
    return True


def upsert_category(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('categoryId') or row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(KvCategory, retailer=retailer, kiotviet_id=kid, incoming_modified=modified):
        return False
    KvCategory.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'parent_kiotviet_id': parse_kv_int(row.get('parentId')),
            'category_name': row.get('categoryName') or '',
            'has_child': bool(row.get('hasChild')),
            'kv_created_at': parse_kv_datetime(row.get('createdDate')),
            'kv_modified_at': parse_kv_datetime(row.get('modifiedDate')),
            'is_deleted': False,
        },
    )
    return True


def _sync_product_children(retailer: str, product_id: int, row: dict) -> None:
    KvProductAttribute.objects.filter(
        retailer=retailer,
        product_kiotviet_id=product_id,
    ).delete()
    for attr in row.get('attributes') or []:
        if not isinstance(attr, dict):
            continue
        KvProductAttribute.objects.create(
            retailer=retailer,
            product_kiotviet_id=product_id,
            attribute_name=attr.get('attributeName') or '',
            attribute_value=attr.get('attributeValue') or '',
        )

    seen_units: set[int] = set()
    for unit in row.get('units') or []:
        if not isinstance(unit, dict):
            continue
        uid = parse_kv_int(unit.get('id'))
        if uid is None:
            continue
        seen_units.add(uid)
        KvProductUnit.objects.update_or_create(
            retailer=retailer,
            kiotviet_id=uid,
            defaults={
                'product_kiotviet_id': product_id,
                'code': unit.get('code') or '',
                'name': unit.get('name') or '',
                'full_name': unit.get('fullName') or '',
                'unit': unit.get('unit') or '',
                'conversion_value': parse_kv_float(unit.get('conversionValue')),
                'base_price': parse_kv_decimal(unit.get('basePrice')),
            },
        )

    for inv in row.get('inventories') or []:
        if not isinstance(inv, dict):
            continue
        branch_id = parse_kv_int(inv.get('branchId'))
        if branch_id is None:
            continue
        on_hand = inv.get('onHand')
        if on_hand is None:
            on_hand = inv.get('onhand')
        KvProductInventory.objects.update_or_create(
            retailer=retailer,
            product_kiotviet_id=product_id,
            branch_kiotviet_id=branch_id,
            defaults={
                'branch_name': inv.get('branchName') or '',
                'on_hand': parse_kv_float(on_hand),
                'reserved': parse_kv_float(inv.get('reserved')),
                'cost': parse_kv_decimal(inv.get('cost')),
                'kv_modified_at': parse_kv_datetime(inv.get('modifiedDate')),
                'is_deleted': False,
            },
        )


def upsert_product(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(KvProduct, retailer=retailer, kiotviet_id=kid, incoming_modified=modified):
        return False
    image_urls = extract_product_image_urls(row)
    KvProduct.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'code': row.get('code') or '',
            'bar_code': row.get('barCode') or '',
            'name': row.get('name') or '',
            'full_name': row.get('fullName') or '',
            'description': row.get('description') or '',
            'category_kiotviet_id': parse_kv_int(row.get('categoryId')),
            'category_name': row.get('categoryName') or '',
            'unit': row.get('unit') or '',
            'base_price': parse_kv_decimal(row.get('basePrice')),
            'weight': parse_kv_float(row.get('weight')),
            'allows_sale': row.get('allowsSale'),
            'has_variants': row.get('hasVariants'),
            'is_active': row.get('isActive'),
            'product_type': parse_kv_int(row.get('productType')),
            'image_urls': image_urls,
            'kv_created_at': parse_kv_datetime(row.get('createdDate')),
            'kv_modified_at': modified,
            'raw_json': row,
            'is_deleted': False,
        },
    )
    _sync_product_children(retailer, kid, row)
    return True


def upsert_customer(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(KvCustomer, retailer=retailer, kiotviet_id=kid, incoming_modified=modified):
        return False
    KvCustomer.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'code': row.get('code') or '',
            'name': row.get('name') or '',
            'gender': row.get('gender'),
            'birth_date': parse_kv_date(row.get('birthDate')),
            'contact_number': row.get('contactNumber') or '',
            'address': row.get('address') or '',
            'location_name': row.get('locationName') or '',
            'ward_name': row.get('wardName') or '',
            'email': row.get('email') or '',
            'organization': row.get('organization') or '',
            'comments': row.get('comments') or '',
            'tax_code': row.get('taxCode') or '',
            'debt': parse_kv_decimal(row.get('debt')),
            'total_invoiced': parse_kv_decimal(row.get('totalInvoiced')),
            'total_revenue': parse_kv_decimal(row.get('totalRevenue')),
            'total_point': parse_kv_float(row.get('totalPoint')),
            'reward_point': parse_kv_int(row.get('rewardPoint')),
            'kv_created_at': parse_kv_datetime(row.get('createdDate')),
            'kv_modified_at': parse_kv_datetime(row.get('modifiedDate')),
            'raw_json': row,
            'is_deleted': False,
        },
    )
    return True


def _sync_transaction_lines(
    *,
    retailer: str,
    parent_id: int,
    details_key: str,
    line_model,
    parent_field: str,
    row: dict,
) -> None:
    details = row.get(details_key) or []
    if not details:
        return
    line_model.objects.filter(retailer=retailer, **{parent_field: parent_id}).delete()
    for idx, item in enumerate(details):
        if not isinstance(item, dict):
            continue
        line_model.objects.create(
            retailer=retailer,
            **{
                parent_field: parent_id,
                'product_kiotviet_id': parse_kv_int(item.get('productId')),
                'product_code': item.get('productCode') or item.get('ProductCode') or '',
                'product_name': item.get('productName') or '',
                'quantity': parse_kv_float(item.get('quantity')),
                'price': parse_kv_decimal(item.get('price')),
                'discount': parse_kv_decimal(item.get('discount')),
                'note': item.get('note') or '',
                'line_index': idx,
            },
        )


def upsert_order(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(KvOrder, retailer=retailer, kiotviet_id=kid, incoming_modified=modified):
        return False
    KvOrder.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'code': row.get('code') or '',
            'purchase_date': parse_kv_datetime(row.get('purchaseDate')),
            'branch_kiotviet_id': parse_kv_int(row.get('branchId')),
            'branch_name': row.get('branchName') or '',
            'sold_by_kiotviet_id': parse_kv_int(row.get('soldById')),
            'sold_by_name': row.get('soldByName') or '',
            'customer_kiotviet_id': parse_kv_int(row.get('customerId')),
            'customer_code': row.get('customerCode') or '',
            'customer_name': row.get('customerName') or '',
            'total': parse_kv_decimal(row.get('total')),
            'total_payment': parse_kv_decimal(row.get('totalPayment')),
            'discount': parse_kv_decimal(row.get('discount')),
            'status': parse_kv_int(row.get('status')),
            'status_value': row.get('statusValue') or '',
            'description': row.get('description') or '',
            'kv_created_at': parse_kv_datetime(row.get('createdDate')),
            'kv_modified_at': parse_kv_datetime(row.get('modifiedDate')),
            'raw_json': row,
            'is_deleted': False,
        },
    )
    _sync_transaction_lines(
        retailer=retailer,
        parent_id=kid,
        details_key='orderDetails',
        line_model=KvOrderLine,
        parent_field='order_kiotviet_id',
        row=row,
    )
    return True


def upsert_invoice(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(KvInvoice, retailer=retailer, kiotviet_id=kid, incoming_modified=modified):
        return False
    KvInvoice.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'code': row.get('code') or '',
            'purchase_date': parse_kv_datetime(row.get('purchaseDate')),
            'branch_kiotviet_id': parse_kv_int(row.get('branchId')),
            'branch_name': row.get('branchName') or '',
            'sold_by_kiotviet_id': parse_kv_int(row.get('soldById')),
            'sold_by_name': row.get('soldByName') or '',
            'customer_kiotviet_id': parse_kv_int(row.get('customerId')),
            'customer_code': row.get('customerCode') or '',
            'customer_name': row.get('customerName') or '',
            'total': parse_kv_decimal(row.get('total')),
            'total_payment': parse_kv_decimal(row.get('totalPayment')),
            'status': parse_kv_int(row.get('status')),
            'status_value': row.get('statusValue') or '',
            'kv_created_at': parse_kv_datetime(row.get('createdDate')),
            'kv_modified_at': parse_kv_datetime(row.get('modifiedDate')),
            'raw_json': row,
            'is_deleted': False,
        },
    )
    _sync_transaction_lines(
        retailer=retailer,
        parent_id=kid,
        details_key='invoiceDetails',
        line_model=KvInvoiceLine,
        parent_field='invoice_kiotviet_id',
        row=row,
    )
    return True


def upsert_purchase_order(retailer: str, row: dict) -> bool:
    kid = parse_kv_int(row.get('id'))
    if kid is None:
        return False
    modified = parse_kv_datetime(row.get('modifiedDate'))
    if not needs_upsert(
        KvPurchaseOrder,
        retailer=retailer,
        kiotviet_id=kid,
        incoming_modified=modified,
    ):
        return False
    KvPurchaseOrder.objects.update_or_create(
        retailer=retailer,
        kiotviet_id=kid,
        defaults={
            'code': row.get('code') or '',
            'purchase_date': parse_kv_datetime(row.get('purchaseDate')),
            'branch_kiotviet_id': parse_kv_int(row.get('branchId')),
            'branch_name': row.get('branchName') or '',
            'supplier_code': row.get('supplierCode') or '',
            'supplier_name': row.get('supplierName') or '',
            'partner_type': row.get('partnerType') or '',
            'purchase_name': row.get('purchaseName') or '',
            'total': parse_kv_decimal(row.get('total')),
            'status': parse_kv_int(row.get('status')),
            'status_value': row.get('statusValue') or '',
            'kv_modified_at': parse_kv_datetime(row.get('modifiedDate')),
            'raw_json': row,
            'is_deleted': False,
        },
    )
    _sync_transaction_lines(
        retailer=retailer,
        parent_id=kid,
        details_key='purchaseOrderDetails',
        line_model=KvPurchaseOrderLine,
        parent_field='purchase_order_kiotviet_id',
        row=row,
    )
    return True


def sync_entity(
    entity: str,
    *,
    full: bool = False,
    client: KiotVietClient | None = None,
    retailer: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    entity = entity.strip().lower()
    retailer = retailer or current_retailer()
    if not retailer:
        return {'entity': entity, 'error': 'KIOTVIET_RETAILER chưa cấu hình'}

    api = client or KiotVietClient()

    paginated_kwargs = {'retailer': retailer, 'full': full, 'on_progress': on_progress}
    if entity == 'branches':
        return _sync_paginated(
            entity_type='branches',
            list_fn=api.list_branches,
            upsert_fn=upsert_branch,
            **paginated_kwargs,
        )
    if entity == 'categories':
        params = {'hierachicalData': 'true'} if full else {}
        return _sync_paginated(
            entity_type='categories',
            list_fn=api.list_categories,
            upsert_fn=upsert_category,
            base_params=params,
            **paginated_kwargs,
        )
    if entity == 'products':
        return _sync_paginated(
            entity_type='products',
            list_fn=api.list_products,
            upsert_fn=upsert_product,
            base_params={'includeInventory': 'true'},
            **paginated_kwargs,
        )
    if entity == 'customers':
        return _sync_paginated(
            entity_type='customers',
            list_fn=api.list_customers,
            upsert_fn=upsert_customer,
            base_params={'includeTotal': 'true'},
            **paginated_kwargs,
        )
    if entity == 'orders':
        return _sync_paginated(
            entity_type='orders',
            list_fn=api.list_orders,
            upsert_fn=upsert_order,
            base_params={'orderBy': 'modifiedDate', 'orderDirection': 'Desc'},
            **paginated_kwargs,
        )
    if entity == 'invoices':
        return _sync_paginated(
            entity_type='invoices',
            list_fn=api.list_invoices,
            upsert_fn=upsert_invoice,
            base_params={'orderBy': 'modifiedDate', 'orderDirection': 'Desc'},
            **paginated_kwargs,
        )
    if entity == 'purchase_orders':
        return _sync_paginated(
            entity_type='purchase_orders',
            list_fn=api.list_purchase_orders,
            upsert_fn=upsert_purchase_order,
            base_params={'orderBy': 'modifiedDate', 'orderDirection': 'Desc'},
            **paginated_kwargs,
        )
    return {'entity': entity, 'error': f'Entity không hỗ trợ: {entity}'}


@transaction.atomic
def sync_all(*, full: bool = False, entities: list[str] | None = None) -> list[dict[str, Any]]:
    order = list(entities or ENTITY_ALL)
    client = KiotVietClient()
    results = []
    for entity in order:
        if entity not in ENTITY_ALL:
            results.append({'entity': entity, 'error': 'Entity không hỗ trợ'})
            continue
        results.append(sync_entity(entity, full=full, client=client))
    return results
