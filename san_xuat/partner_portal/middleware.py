from django.conf import settings


def is_partner_host(request) -> bool:
    host = (request.get_host() or '').split(':')[0].lower()
    return host in getattr(settings, 'PARTNER_PORTAL_HOSTS', set())


class PartnerPortalHostMiddleware:
    """Host pn.* → urlconf cổng đối tác + gắn request.gc_account.

    Cookie theo host (không đặt SESSION_COOKIE_DOMAIN) nên phiên pn không chứa user portal;
    các middleware portal nội bộ phía sau thấy AnonymousUser và cho qua.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_partner_portal = is_partner_host(request)
        request.gc_account = None
        if request.is_partner_portal:
            from san_xuat.partner_portal.auth import get_session_account

            request.urlconf = 'san_xuat.partner_portal.urls'
            request.gc_account = get_session_account(request)
        return self.get_response(request)
