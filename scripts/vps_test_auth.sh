#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T -w /app web python <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_active=True).order_by("-is_superuser", "id").first()
client = Client(HTTP_HOST="portal.justplay.vn", secure=True)
client.force_login(user)

paths = [
    "/",
    "/yeu-cau/de-xuat/cua-toi/",
    "/yeu-cau/de-xuat/cho-xu-ly/",
    "/yeu-cau/de-xuat/tao/",
    "/yeu-cau/ho-tro/cua-toi/",
    "/thiet-bi/it/danh-sach/",
]
for path in paths:
    r = client.get(path, follow=True)
    print(f"{path} -> {r.status_code} (chain len {len(r.redirect_chain)})")
    if r.status_code >= 500:
        print(r.content.decode("utf-8", errors="replace")[:4000])
PY
