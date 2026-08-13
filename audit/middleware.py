import time

from audit.retention import maybe_purge_old_activity_logs
from audit.summaries import CLICKED_BUTTON_COOKIE, is_background_audit_url
from audit.utils import log_from_request, should_skip_audit


def _clear_clicked_button_cookie(request, response):
    if request.COOKIES.get(CLICKED_BUTTON_COOKIE):
        response.delete_cookie(CLICKED_BUTTON_COOKIE, path='/')
    return response


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

        if not is_background_audit_url(request):
            response = _clear_clicked_button_cookie(request, response)
            maybe_purge_old_activity_logs()

        return response
