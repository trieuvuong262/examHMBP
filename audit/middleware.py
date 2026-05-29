import time

from audit.utils import log_from_request, should_skip_audit


class ActivityAuditMiddleware:
    """Ghi nhật ký thao tác HTTP sau mỗi request (trừ static/media)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if should_skip_audit(request):
            return self.get_response(request)

        started = time.monotonic()
        response = self.get_response(request)
        duration_ms = int((time.monotonic() - started) * 1000)

        try:
            log_from_request(request, response, duration_ms)
        except Exception:
            pass

        return response
