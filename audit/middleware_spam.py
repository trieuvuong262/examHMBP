"""Chặn IP spam / quét exploit trước khi xử lý request."""

from django.shortcuts import render

from audit.login_security import block_ip_for_form_spam, is_ip_blocked, it_contact_display, max_ip_attempts
from audit.models import UserActivityLog
from audit.spam_detection import detect_security_scan, should_skip_spam_guard
from audit.utils import create_activity_log, get_client_ip

REASON_LABELS = {
    'exploit_path': 'path exploit',
    'scanner_ua': 'scanner UA',
    'malicious_payload': 'payload độc',
    'garbage_form_fields': 'form rác',
    'login_abuse': 'login exploit',
}


class SpamIpGuardMiddleware:
    """Chặn IP đã block + tự block IP quét bảo mật / spam form."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if should_skip_spam_guard(request):
            return self.get_response(request)

        ip = get_client_ip(request)
        if is_ip_blocked(ip):
            return self._blocked_response(request, kind='ip')

        is_threat, reason, details = detect_security_scan(request)
        if is_threat and ip:
            block_ip_for_form_spam(ip, sample_fields=details, reason=reason)
            label = REASON_LABELS.get(reason, reason)
            try:
                create_activity_log(
                    request=request,
                    action=UserActivityLog.ACTION_OTHER,
                    summary=f'Chặn IP {label} — [{", ".join(str(d) for d in details[:4])}]',
                    path=request.path,
                    method=request.method,
                    status_code=403,
                    request_data={'spam_reason': reason, 'spam_details': details[:12]},
                    extra={'spam_block': True, 'spam_reason': reason, 'spam_details': details[:12]},
                )
            except Exception:
                pass
            return self._blocked_response(request, kind='ip')

        return self.get_response(request)

    def _blocked_response(self, request, *, kind: str):
        accept = (request.headers.get('Accept') or '').lower()
        if 'text/html' in accept or request.path.startswith('/accounts/'):
            return render(
                request,
                'registration/login_lockout.html',
                {
                    'lockout_kind': kind,
                    'locked_user': None,
                    'it_contact': it_contact_display(),
                    'max_attempts': max_ip_attempts(),
                },
                status=403,
            )
        from django.http import HttpResponse

        return HttpResponse('Forbidden', status=403)
