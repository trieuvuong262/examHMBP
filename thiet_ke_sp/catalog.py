"""Nhóm sản phẩm theo danh mục Loại mã của Kho sản phẩm.

Nhóm sản phẩm = phần mã trước dấu «-» (SET-SC → SET, ACC-BALO → ACC, TEE → TEE).
"""

from __future__ import annotations

import re

from django.core.cache import cache
from django.db.models import Q

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


GROUP_CODE_RE = re.compile(r'^[A-Z0-9]{2,16}$')


def normalize_group_code(code: str) -> str:
    return (code or '').strip().upper()


def group_exists(code: str) -> bool:
    return CatalogType.objects.filter(Q(code=code) | Q(code__startswith=f'{code}-')).exists()


def create_group(code: str, name: str) -> str:
    """Thêm nhóm mới = Loại mã mới trong danh mục Kho sản phẩm; trả về mã nhóm."""
    ptype, _created = CatalogType.objects.get_or_create(code=code, defaults={'name': name.strip()})
    cache.delete(_LABELS_CACHE_KEY)
    return group_code(ptype.code)
