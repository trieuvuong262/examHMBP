"""Tìm kiếm server-side cho danh sách có phân trang."""

from django.db.models import Q


def get_search_query(request, param: str = 'q') -> str:
    return (request.GET.get(param) or '').strip()


def search_terms(query: str) -> list[str]:
    return [part for part in (query or '').split() if part]


def apply_term_search(queryset, query: str, *lookups: str):
    """Mỗi từ khóa phải khớp ít nhất một trường (AND giữa các từ)."""
    terms = search_terms(query)
    if not terms:
        return queryset
    for term in terms:
        q_obj = Q()
        for lookup in lookups:
            q_obj |= Q(**{lookup: term})
        queryset = queryset.filter(q_obj)
    return queryset.distinct()


def apply_combined_search(queryset, query: str, build_q_for_term):
    """Mỗi từ khóa: build_q_for_term(term) trả về Q — gộp nhiều nhóm trường."""
    terms = search_terms(query)
    if not terms:
        return queryset
    for term in terms:
        queryset = queryset.filter(build_q_for_term(term))
    return queryset.distinct()


def apply_user_search(queryset, query: str, *, prefix: str = ''):
    """Tìm user theo account, tên, email, mã NS, SĐT — prefix vd. assignee__, requester__."""
    from hrm.phone import is_valid_vn_mobile, normalize_phone

    lookups = (
        f'{prefix}username__icontains',
        f'{prefix}first_name__icontains',
        f'{prefix}last_name__icontains',
        f'{prefix}email__icontains',
        f'{prefix}profile__full_name__icontains',
        f'{prefix}profile__employee_code__icontains',
        f'{prefix}profile__phone__icontains',
    )
    qs = apply_term_search(queryset, query, *lookups)
    phone = normalize_phone(query)
    if is_valid_vn_mobile(phone):
        qs = (qs | queryset.filter(**{f'{prefix}profile__phone': phone})).distinct()
    return qs
