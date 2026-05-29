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
    """Tìm user theo account, tên, email, mã NS — prefix vd. assignee__, requester__."""
    lookups = (
        f'{prefix}username__icontains',
        f'{prefix}first_name__icontains',
        f'{prefix}last_name__icontains',
        f'{prefix}email__icontains',
        f'{prefix}profile__full_name__icontains',
        f'{prefix}profile__employee_code__icontains',
    )
    return apply_term_search(queryset, query, *lookups)
