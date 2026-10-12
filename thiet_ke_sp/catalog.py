"""Nhóm / loại sản phẩm theo danh mục Loại mã của Kho sản phẩm.

Loại sản phẩm = một Loại mã (TEE, SET-SC, ACC-BALO…). Nhóm sản phẩm = phần mã trước dấu «-»
(SET-SC → SET, ACC-BALO → ACC, TEE → TEE).
"""

from __future__ import annotations

from django.core.cache import cache

from kho_san_pham.catalog_models import ProductType as CatalogType

_LABELS_CACHE_KEY = 'tksp:product_group_labels'
_LABELS_CACHE_SECONDS = 60


def group_code(type_code: str) -> str:
    return (type_code or '').strip().upper().split('-', 1)[0]


def _groups(types) -> list[tuple[str, str]]:
    names = {t.code: t.name for t in types}
    children: dict[str, list[str]] = {}
    for t in types:
        children.setdefault(group_code(t.code), []).append(t.name)
    return [(code, f'{code} — {names.get(code) or " / ".join(kids)}') for code, kids in children.items()]


def group_choices() -> list[tuple[str, str]]:
    return _groups(list(CatalogType.objects.filter(is_active=True)))


def group_labels() -> dict[str, str]:
    labels = cache.get(_LABELS_CACHE_KEY)
    if labels is None:
        labels = dict(_groups(list(CatalogType.objects.all())))
        cache.set(_LABELS_CACHE_KEY, labels, _LABELS_CACHE_SECONDS)
    return labels


def group_label(code: str) -> str:
    if not code:
        return ''
    return group_labels().get(code, code)


def type_queryset(include_pk=None):
    qs = CatalogType.objects.filter(is_active=True)
    if include_pk:
        qs = CatalogType.objects.filter(pk=include_pk) | qs
    return qs.order_by('sort_order', 'code')
