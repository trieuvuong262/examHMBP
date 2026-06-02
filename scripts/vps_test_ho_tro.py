"""Test /yeu-cau/ho-tro/ on VPS."""
import os
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

user = get_user_model().objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST="portal.justplay.vn", secure=True)
c.force_login(user)

paths = [
    "/yeu-cau/ho-tro/",
    "/yeu-cau/ho-tro/cua-toi/",
    "/yeu-cau/ho-tro/cho-xu-ly/",
    "/yeu-cau/ho-tro/tao/it/",
]

for path in paths:
    try:
        r = c.get(path, follow=True)
        print(path, "->", r.status_code, r.request.get("PATH_INFO", ""))
        if r.status_code >= 500:
            print(r.content[:1500].decode("utf-8", errors="replace"))
    except Exception:
        print(path, "-> EXCEPTION")
        traceback.print_exc()
