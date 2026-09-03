from san_xuat.list_filter_persist import maybe_redirect_sx_list_filters


class SxListFilterPersistMiddleware:
    """Giữ bộ lọc list Sản xuất khi bấm Quay lại từ chi tiết / form."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        redirected = maybe_redirect_sx_list_filters(request)
        if redirected is not None:
            return redirected
        return self.get_response(request)
