"""Web App Manifest for Add to Home Screen / PWA shortcuts."""
import json

from django.http import HttpResponse
from django.templatetags.static import static
from django.views.decorators.http import require_GET


@require_GET
def site_manifest(request):
    icon_base = request.build_absolute_uri(static("images/logo/"))
    data = {
        "id": "/",
        "name": "JustPlay Portal",
        "short_name": "JustPlay",
        "description": "Cổng thông tin nội bộ JustPlay",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#ffffff",
        "theme_color": "#dc2626",
        "lang": "vi",
        "icons": [
            {
                "src": icon_base + "icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": icon_base + "icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": icon_base + "icon-512-maskable.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": icon_base + "apple-touch-icon.png",
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any",
            },
        ],
    }
    return HttpResponse(
        json.dumps(data, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )
