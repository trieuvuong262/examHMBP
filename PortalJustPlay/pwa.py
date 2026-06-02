"""Web App Manifest + Service Worker cho PWA (Edge/Chrome Install app)."""
import json
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.templatetags.static import static
from django.views.decorators.http import require_GET


def _portal_origin(request) -> str:
    base = (getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '') or '').rstrip('/')
    if base:
        return base
    return request.build_absolute_uri('/').rstrip('/')


@require_GET
def site_manifest(request):
    origin = _portal_origin(request)
    icon_base = f'{origin}{static("images/logo/")}'
    data = {
        'id': f'{origin}/',
        'name': 'JustPlay Portal',
        'short_name': 'JustPlay',
        'description': 'Cổng thông tin nội bộ JustPlay',
        'start_url': f'{origin}/',
        'scope': f'{origin}/',
        'display': 'standalone',
        'display_override': ['standalone', 'browser'],
        'orientation': 'any',
        'background_color': '#ffffff',
        'theme_color': '#dc2626',
        'lang': 'vi',
        'prefer_related_applications': False,
        'icons': [
            {
                'src': icon_base + 'icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': icon_base + 'icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': icon_base + 'icon-512-maskable.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
    }
    return HttpResponse(
        json.dumps(data, ensure_ascii=False),
        content_type='application/manifest+json; charset=utf-8',
    )


@require_GET
def portal_service_worker(request):
    """SW tại /sw.js — scope / cho Chrome/Edge cài PWA."""
    sw_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'portal-sw.js'
    content = sw_path.read_text(encoding='utf-8')
    response = HttpResponse(content, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response
