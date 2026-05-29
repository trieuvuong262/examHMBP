from django.core.paginator import Paginator

LIST_PAGE_SIZE = 30


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
