"""Tìm kiếm thông minh NPL — nhiều từ, không dấu, nhiều trường."""

from __future__ import annotations

import re
import unicodedata

from django.db.models import Q

from PortalJustPlay.list_search import apply_combined_search, search_terms

# Ký tự có thể thay thế khi tìm không dấu (PostgreSQL __iregex).
_ACCENT_CLASSES = {
    'a': 'aàáảãạăằắẳẵặâầấẩẫậ',
    'd': 'dđ',
    'e': 'eèéẻẽẹêềếểễệ',
    'i': 'iìíỉĩị',
    'o': 'oòóỏõọôồốổỗộơờớởỡợ',
    'u': 'uùúủũụưừứửữự',
    'y': 'yỳýỷỹỵ',
}

MATERIAL_SEARCH_FIELDS = (
    'code',
    'name',
    'color__name',
    'color__code',
    'specification__name',
    'specification__code',
    'category__name',
    'category__parent__name',
    'unit__name',
    'unit__code',
    'supplier__name',
    'supplier__code',
)


def normalize_search_text(text: str) -> str:
    text = unicodedata.normalize('NFD', (text or '').lower())
    text = text.replace('đ', 'd')
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')


def _vietnamese_flexible_pattern(term: str) -> str:
    """Regex khớp có/không dấu — dùng với __iregex."""
    term = (term or '').strip()
    if not term:
        return ''
    pieces: list[str] = []
    for ch in term:
        lower = ch.lower()
        if lower in _ACCENT_CLASSES:
            pieces.append(f'[{_ACCENT_CLASSES[lower]}]')
        else:
            pieces.append(re.escape(ch))
    return ''.join(pieces)


def material_q_for_term(term: str, *, prefix: str = '') -> Q:
    """Một từ khóa khớp ít nhất một trường NPL."""
    pattern = _vietnamese_flexible_pattern(term)
    if not pattern:
        return Q()
    q = Q()
    for field in MATERIAL_SEARCH_FIELDS:
        q |= Q(**{f'{prefix}{field}__iregex': pattern})
    return q


def balance_stock_q_for_term(term: str) -> Q:
    """Tìm thẻ kho — NPL hoặc vị trí kho."""
    pattern = _vietnamese_flexible_pattern(term)
    if not pattern:
        return Q()
    return material_q_for_term(term, prefix='material__') | Q(
        location__code__iregex=pattern,
    ) | Q(
        location__name__iregex=pattern,
    )


def apply_material_search(queryset, query: str):
    """Mỗi từ trong query phải khớp ít nhất một trường (AND giữa các từ)."""
    return apply_combined_search(queryset, query, material_q_for_term)


def material_search_haystack(material) -> str:
    parts = [
        getattr(material, 'code', '') or '',
        getattr(material, 'name', '') or '',
    ]
    color = getattr(material, 'color', None)
    if color is not None:
        parts.extend([getattr(color, 'name', '') or '', getattr(color, 'code', '') or ''])
    spec = getattr(material, 'specification', None)
    if spec is not None:
        parts.extend([getattr(spec, 'name', '') or '', getattr(spec, 'code', '') or ''])
    category = getattr(material, 'category', None)
    if category is not None:
        parts.append(getattr(category, 'name', '') or '')
        parent = getattr(category, 'parent', None)
        if parent is not None:
            parts.append(getattr(parent, 'name', '') or '')
    unit = getattr(material, 'unit', None)
    if unit is not None:
        parts.extend([getattr(unit, 'name', '') or '', getattr(unit, 'code', '') or ''])
    supplier = getattr(material, 'supplier', None)
    if supplier is not None:
        parts.extend([getattr(supplier, 'name', '') or '', getattr(supplier, 'code', '') or ''])
    return normalize_search_text(' '.join(parts))


def material_matches_query(material, query: str) -> bool:
    """Lọc trong bộ nhớ — cùng logic với apply_material_search."""
    terms = search_terms(query)
    if not terms:
        return True
    haystack = material_search_haystack(material)
    return all(normalize_search_text(term) in haystack for term in terms)
