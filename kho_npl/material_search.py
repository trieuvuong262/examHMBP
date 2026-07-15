"""Tìm kiếm thông minh Kho NPL — không dấu, thiếu dấu cách, nhiều từ."""

from __future__ import annotations

import re
import unicodedata

from django.db.models import CharField, Q, TextField, Value
from django.db.models.expressions import Func
from django.db.models.functions import Cast, Coalesce, Concat, Lower

from PortalJustPlay.list_search import search_terms

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

MATERIAL_SEARCH_FIELDS = ('name', 'code', 'variant_group')

# Ô chọn NPL trong phiếu: chỉ khớp theo mã và tên NPL.
MATERIAL_DOC_SEARCH_FIELDS = ('name', 'code')


class _RegexpReplace(Func):
    function = 'REGEXP_REPLACE'
    output_field = CharField()


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


def _fields_q_simple(term: str, fields: tuple[str, ...], *, prefix: str = '') -> Q:
    pattern = _vietnamese_flexible_pattern(term)
    if not pattern:
        return Q()
    q = Q()
    for field in fields:
        q |= Q(**{f'{prefix}{field}__iregex': pattern})
    return q


def _missing_space_split_q(term: str, fields: tuple[str, ...], *, prefix: str = '') -> Q:
    """Gõ liền (vd. vaitrang) — tách 2 phần, mỗi phần khớp ít nhất một trường."""
    compact = normalize_search_text(term.replace(' ', ''))
    if len(compact) < 4:
        return Q()
    q = Q()
    for split_at in range(2, len(compact) - 1):
        left, right = compact[:split_at], compact[split_at:]
        q |= _fields_q_simple(left, fields, prefix=prefix) & _fields_q_simple(right, fields, prefix=prefix)
    return q


def q_for_term_on_fields(term: str, fields: tuple[str, ...], *, prefix: str = '') -> Q:
    q = _fields_q_simple(term, fields, prefix=prefix)
    if ' ' not in term:
        q |= _missing_space_split_q(term, fields, prefix=prefix)
    return q


def material_q_for_term(term: str, *, prefix: str = '') -> Q:
    return q_for_term_on_fields(term, MATERIAL_SEARCH_FIELDS, prefix=prefix)


def _single_field_blob_expr(field_path: str):
    blob = Lower(Cast(Coalesce(field_path, Value('')), TextField()))
    return _RegexpReplace(blob, Value(r'\s+'), Value(''), Value('g'))


def _annotate_name_blob(queryset, *, prefix: str = ''):
    field_path = f'{prefix}name' if prefix else 'name'
    blob_field = f'{prefix}_jp_mat_blob' if prefix else '_jp_mat_blob'
    if blob_field in queryset.query.annotations:
        return queryset
    return queryset.annotate(**{blob_field: _single_field_blob_expr(field_path)})


def _q_is_empty(q: Q) -> bool:
    return not q.children


def _apply_or_term_search(queryset, query: str, build_q_for_term):
    """Mỗi từ khóa OR với nhau — chỉ cần khớp một từ là hiện."""
    terms = search_terms(query)
    if not terms:
        return queryset.none()
    q = Q()
    has_filter = False
    for term in terms:
        term_q = build_q_for_term(term)
        if _q_is_empty(term_q):
            continue
        q |= term_q
        has_filter = True
    if not has_filter:
        return queryset.none()
    return queryset.filter(q).distinct()


def _term_hits_text(term: str, haystack: str) -> bool:
    """Một từ khóa khớp tên NPL — substring, từ đơn, hoặc gõ liền."""
    norm_term = normalize_search_text(term)
    if not norm_term:
        return False
    if norm_term in haystack:
        return True
    compact_term = norm_term.replace(' ', '')
    haystack_compact = haystack.replace(' ', '')
    if compact_term and compact_term in haystack_compact:
        return True
    for word in haystack.split():
        if norm_term in word or (len(norm_term) >= 2 and word.startswith(norm_term)):
            return True
    if ' ' not in term and len(compact_term) >= 4:
        for split_at in range(2, len(compact_term) - 1):
            left, right = compact_term[:split_at], compact_term[split_at:]
            if left in haystack and right in haystack:
                return True
    return False


def _name_compact_q(query: str, *, prefix: str = '') -> Q:
    compact = normalize_search_text(query.replace(' ', ''))
    if len(compact) < 3:
        return Q()
    pattern = _vietnamese_flexible_pattern(compact)
    if not pattern:
        return Q()
    blob_field = f'{prefix}_jp_mat_blob' if prefix else '_jp_mat_blob'
    return Q(**{f'{blob_field}__iregex': pattern})


def apply_smart_search(
    queryset,
    query: str,
    fields: tuple[str, ...],
    *,
    prefix: str = '',
):
    """Tìm thông minh — OR giữa các từ (khớp một từ là hiện), OR giữa các trường."""
    query = (query or '').strip()
    if not query or not fields:
        return queryset

    def build_q(term: str) -> Q:
        return q_for_term_on_fields(term, fields, prefix=prefix)

    matched = _apply_or_term_search(queryset, query, build_q)

    # Gõ liền trên một trường tên: khớp chuỗi gộp không khoảng trắng
    if ' ' not in query and len(fields) == 1 and fields[0] == 'name':
        compact = normalize_search_text(query)
        if len(compact) >= 3:
            compact_q = _name_compact_q(query, prefix=prefix)
            if not _q_is_empty(compact_q):
                compact_qs = _annotate_name_blob(queryset, prefix=prefix).filter(compact_q)
                matched = queryset.filter(
                    Q(pk__in=matched.values('pk')) | Q(pk__in=compact_qs.values('pk')),
                ).distinct()

    return matched


def apply_material_search(queryset, query: str):
    """Tìm NPL — theo tên, mã và tên nhóm hàng."""
    return apply_smart_search(queryset, query, MATERIAL_SEARCH_FIELDS)


def apply_material_search_strict(queryset, query: str):
    """
    Tìm NPL cho ô chọn trong phiếu — chỉ theo mã và tên NPL.

    Tất cả các từ đều phải khớp (AND giữa các từ), mỗi từ vẫn linh hoạt
    có/không dấu và gõ liền. Khác tìm thông minh (OR) nên không hiện lan man.
    """
    query = (query or '').strip()
    if not query:
        return queryset
    terms = search_terms(query)
    if not terms:
        return queryset.none()
    qs = queryset
    has_filter = False
    for term in terms:
        term_q = q_for_term_on_fields(term, MATERIAL_DOC_SEARCH_FIELDS)
        if _q_is_empty(term_q):
            continue
        qs = qs.filter(term_q)
        has_filter = True
    if not has_filter:
        return queryset.none()
    return qs.distinct()


def material_relevance_sort_key(material, query: str):
    """Xếp hạng kết quả cho ô chọn trong phiếu — mã/tên khớp chính xác lên đầu."""
    q_norm = normalize_search_text((query or '').strip())
    code = normalize_search_text(getattr(material, 'code', '') or '')
    name = normalize_search_text(getattr(material, 'name', '') or '')
    if not q_norm:
        rank = 5
    elif code == q_norm or name == q_norm:
        rank = 0
    elif code.startswith(q_norm) or name.startswith(q_norm):
        rank = 1
    elif q_norm in name or q_norm in code:
        rank = 2
    elif q_norm.replace(' ', '') in name.replace(' ', ''):
        rank = 3
    else:
        rank = 4
    return (rank, name, code)


def material_search_haystack(material) -> str:
    parts = [
        getattr(material, 'name', '') or '',
        getattr(material, 'code', '') or '',
        getattr(material, 'variant_group', '') or '',
    ]
    return normalize_search_text(' '.join(parts))


def material_matches_query(material, query: str) -> bool:
    """Lọc trong bộ nhớ — cùng logic với apply_material_search (tên / mã / nhóm hàng)."""
    if not query or not query.strip():
        return True
    haystack = material_search_haystack(material)
    terms = search_terms(query)
    if not terms:
        terms = [query.strip()]
    return any(_term_hits_text(term, haystack) for term in terms)
