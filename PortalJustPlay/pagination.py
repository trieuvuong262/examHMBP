from django.core.paginator import Paginator

LIST_PAGE_SIZE = 30


def pagination_href(query_string: str, page_param: str, page_number: int) -> str:
    """URL query cho một trang (giữ bộ lọc hiện tại)."""
    qs = (query_string or '').strip()
    page_param = page_param or 'page'
    if qs:
        return f'?{qs}&{page_param}={page_number}'
    return f'?{page_param}={page_number}'


def pagination_link_items(page_obj, *, window: int = 2, edge: int = 1) -> list[int | None]:
    """
    Danh sách số trang kèm None = dấu …
    Ví dụ: [1, None, 4, 5, 6, None, 20]
    """
    num_pages = page_obj.paginator.num_pages
    if num_pages <= 1:
        return []
    current = page_obj.number
    max_compact = window * 2 + edge * 2 + 3
    if num_pages <= max_compact:
        return list(range(1, num_pages + 1))

    pages: set[int] = set()
    for n in range(1, edge + 1):
        pages.add(n)
    for n in range(num_pages - edge + 1, num_pages + 1):
        pages.add(n)
    for n in range(current - window, current + window + 1):
        if 1 <= n <= num_pages:
            pages.add(n)

    items: list[int | None] = []
    prev: int | None = None
    for n in sorted(pages):
        if prev is not None and n - prev > 1:
            items.append(None)
        items.append(n)
        prev = n
    return items


def paginate_queryset(request, queryset, *, page_param='page', per_page=LIST_PAGE_SIZE):
    """Phân trang queryset; trả về (page_obj, query_string không gồm tham số trang)."""
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get(page_param))
    params = request.GET.copy()
    if page_param in params:
        del params[page_param]
    return page_obj, params.urlencode()


def paginate_columns(request, column_specs, *, per_page=LIST_PAGE_SIZE):
    """
    Phân trang nhiều cột (kanban).
    column_specs: list các tuple (tên, queryset, page_param)
    Trả về (dict tên -> page_obj, query_string chung không gồm tham số trang cột).
    """
    page_params = {spec[2] for spec in column_specs}
    base_params = request.GET.copy()
    for param in page_params:
        if param in base_params:
            del base_params[param]
    base_query = base_params.urlencode()

    pages = {}
    for name, queryset, page_param in column_specs:
        paginator = Paginator(queryset, per_page)
        pages[name] = paginator.get_page(request.GET.get(page_param))
    return pages, base_query
