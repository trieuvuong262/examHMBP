from kho_npl.stock_domain import bind_request, domain_from_path, reset_request


class StockDomainMiddleware:
    """Gắn request.stock_domain và contextvar cho reverse/queryset kho."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.stock_domain = domain_from_path(request.path)
        token = bind_request(request)
        try:
            return self.get_response(request)
        finally:
            reset_request(token)
