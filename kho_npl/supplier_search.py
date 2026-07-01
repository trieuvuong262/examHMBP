"""Tìm kiếm nhà cung cấp — server-side cho TomSelect."""

from django.db.models import Q

from kho_npl.models import Supplier


def supplier_select_label(supplier: Supplier) -> str:
    label = f'{supplier.name} ({supplier.code})'
    if supplier.phone:
        label += f' — {supplier.phone}'
    return label


def search_suppliers(query: str, *, limit: int | None = None) -> list[dict]:
    qs = Supplier.objects.filter(is_active=True)
    q = (query or '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(code__icontains=q)
            | Q(phone__icontains=q),
        )
    if limit is None:
        limit = 1000 if not q else 50
    qs = qs.order_by('name')[:limit]
    return [
        {
            'id': supplier.pk,
            'text': supplier_select_label(supplier),
            'name': supplier.name,
            'code': supplier.code,
            'phone': supplier.phone or '',
        }
        for supplier in qs
    ]
