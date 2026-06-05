"""Tra cứu từ mirror kv_* thay vì gọi API trực tiếp."""

from __future__ import annotations

from django.db.models import Q

from .models import (
    KvCustomer,
    KvInvoice,
    KvOrder,
    KvProduct,
    KvProductInventory,
    KvPurchaseOrder,
)
from .sync_service import current_retailer


def _active(qs, retailer: str):
    return qs.filter(retailer=retailer, is_deleted=False)


def browse_customers(
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    name: str = '',
    code: str = '',
    contact_number: str = '',
) -> tuple[list[dict], int]:
    retailer = retailer or current_retailer()
    qs = _active(KvCustomer.objects.all(), retailer).order_by('name', 'kiotviet_id')
    if code:
        qs = qs.filter(code__iexact=code.strip())
    elif contact_number:
        qs = qs.filter(contact_number__icontains=contact_number.strip())
    elif name:
        qs = qs.filter(name__icontains=name.strip())
    total = qs.count()
    offset = (max(page, 1) - 1) * per_page
    rows = [obj.to_api_dict() for obj in qs[offset : offset + per_page]]
    return rows, total


def get_customer(retailer: str, customer_id: int) -> dict | None:
    obj = KvCustomer.objects.filter(
        retailer=retailer,
        kiotviet_id=customer_id,
        is_deleted=False,
    ).first()
    return obj.to_api_dict() if obj else None


def get_customer_by_code(retailer: str, code: str) -> dict | None:
    obj = KvCustomer.objects.filter(
        retailer=retailer,
        code__iexact=code.strip(),
        is_deleted=False,
    ).first()
    return obj.to_api_dict() if obj else None


def browse_products(
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    name: str = '',
    code: str = '',
    bar_code: str = '',
) -> tuple[list[dict], int]:
    retailer = retailer or current_retailer()
    qs = _active(KvProduct.objects.all(), retailer).order_by('name', 'kiotviet_id')
    if code:
        qs = qs.filter(code__iexact=code.strip())
    elif bar_code:
        qs = qs.filter(bar_code__iexact=bar_code.strip())
    elif name:
        qs = qs.filter(Q(name__icontains=name.strip()) | Q(full_name__icontains=name.strip()))
    total = qs.count()
    offset = (max(page, 1) - 1) * per_page
    rows = [obj.to_api_dict(include_inventory=True) for obj in qs[offset : offset + per_page]]
    return rows, total


def get_product(retailer: str, product_id: int) -> dict | None:
    obj = KvProduct.objects.filter(
        retailer=retailer,
        kiotviet_id=product_id,
        is_deleted=False,
    ).first()
    return obj.to_api_dict(include_inventory=True) if obj else None


def get_product_by_code(retailer: str, code: str) -> dict | None:
    obj = KvProduct.objects.filter(
        retailer=retailer,
        code__iexact=code.strip(),
        is_deleted=False,
    ).first()
    return obj.to_api_dict(include_inventory=True) if obj else None


def browse_stock(
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    product_code: str = '',
    product_name: str = '',
) -> tuple[list[dict], int]:
    retailer = retailer or current_retailer()
    inv_qs = _active(KvProductInventory.objects.all(), retailer).select_related()
    if product_code:
        product_ids = KvProduct.objects.filter(
            retailer=retailer,
            code__iexact=product_code.strip(),
            is_deleted=False,
        ).values_list('kiotviet_id', flat=True)
        inv_qs = inv_qs.filter(product_kiotviet_id__in=product_ids)
    elif product_name:
        product_ids = KvProduct.objects.filter(
            retailer=retailer,
            is_deleted=False,
        ).filter(
            Q(name__icontains=product_name.strip()) | Q(full_name__icontains=product_name.strip()),
        ).values_list('kiotviet_id', flat=True)
        inv_qs = inv_qs.filter(product_kiotviet_id__in=product_ids)

    inv_qs = inv_qs.order_by('product_kiotviet_id', 'branch_kiotviet_id')
    total = inv_qs.count()
    offset = (max(page, 1) - 1) * per_page
    page_invs = list(inv_qs[offset : offset + per_page])
    product_ids = {inv.product_kiotviet_id for inv in page_invs}
    products = {
        p.kiotviet_id: p
        for p in KvProduct.objects.filter(retailer=retailer, kiotviet_id__in=product_ids)
    }
    rows: list[dict] = []
    for inv in page_invs:
        product = products.get(inv.product_kiotviet_id)
        if not product:
            continue
        pdata = product.to_api_dict(include_inventory=False)
        pdata['inventories'] = [inv.to_api_dict()]
        rows.append(pdata)
    return rows, total


def _browse_transactions(
    model,
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    code: str = '',
    customer_code: str = '',
) -> tuple[list[dict], int]:
    retailer = retailer or current_retailer()
    qs = _active(model.objects.all(), retailer).order_by('-purchase_date', '-kiotviet_id')
    if code:
        qs = qs.filter(code__iexact=code.strip())
    elif customer_code:
        qs = qs.filter(customer_code__iexact=customer_code.strip())
    total = qs.count()
    offset = (max(page, 1) - 1) * per_page
    rows = [obj.to_api_dict(include_lines=False) for obj in qs[offset : offset + per_page]]
    return rows, total


def browse_orders(**kwargs) -> tuple[list[dict], int]:
    return _browse_transactions(KvOrder, **kwargs)


def browse_invoices(**kwargs) -> tuple[list[dict], int]:
    return _browse_transactions(KvInvoice, **kwargs)


def get_order(retailer: str, order_id: int) -> dict | None:
    obj = KvOrder.objects.filter(retailer=retailer, kiotviet_id=order_id, is_deleted=False).first()
    return obj.to_api_dict(include_lines=True) if obj else None


def get_order_by_code(retailer: str, code: str) -> dict | None:
    obj = KvOrder.objects.filter(
        retailer=retailer,
        code__iexact=code.strip(),
        is_deleted=False,
    ).first()
    return obj.to_api_dict(include_lines=True) if obj else None


def get_invoice(retailer: str, invoice_id: int) -> dict | None:
    obj = KvInvoice.objects.filter(retailer=retailer, kiotviet_id=invoice_id, is_deleted=False).first()
    return obj.to_api_dict(include_lines=True) if obj else None


def get_invoice_by_code(retailer: str, code: str) -> dict | None:
    obj = KvInvoice.objects.filter(
        retailer=retailer,
        code__iexact=code.strip(),
        is_deleted=False,
    ).first()
    return obj.to_api_dict(include_lines=True) if obj else None


def browse_purchase_orders(
    *,
    page: int,
    per_page: int,
    retailer: str | None = None,
    code: str = '',
) -> tuple[list[dict], int]:
    retailer = retailer or current_retailer()
    qs = _active(KvPurchaseOrder.objects.all(), retailer).order_by('-purchase_date', '-kiotviet_id')
    if code:
        qs = qs.filter(code__iexact=code.strip())
    total = qs.count()
    offset = (max(page, 1) - 1) * per_page
    rows = [obj.to_api_dict(include_lines=False) for obj in qs[offset : offset + per_page]]
    return rows, total


def get_purchase_order(retailer: str, purchase_id: int) -> dict | None:
    obj = KvPurchaseOrder.objects.filter(
        retailer=retailer,
        kiotviet_id=purchase_id,
        is_deleted=False,
    ).first()
    return obj.to_api_dict(include_lines=True) if obj else None
