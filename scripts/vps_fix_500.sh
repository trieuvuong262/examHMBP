#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay

echo "==> Git HEAD"
git rev-parse --short HEAD

echo "==> Rebuild web + migrate"
docker compose up -d --build web
docker compose exec -T web python manage.py migrate --noinput
docker compose exec -T web python manage.py collectstatic --noinput

echo "==> Test URLs (internal)"
docker compose exec -T -w /app web python <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_active=True).order_by("-is_superuser", "id").first()
client = Client(HTTP_HOST="portal.justplay.vn")
if user:
    client.force_login(user)

for path in ["/accounts/login/", "/", "/yeu-cau/de-xuat/cua-toi/", "/thiet-bi/it/danh-sach/"]:
    try:
        r = client.get(path)
        print(f"{path} -> {r.status_code}")
        if r.status_code >= 500:
            body = r.content.decode("utf-8", errors="replace")[:3000]
            print(body)
    except Exception as e:
        print(f"{path} -> EXC: {e}")
PY

echo "==> External HTTPS"
curl -sk -o /dev/null -w "login:%{http_code}\n" https://portal.justplay.vn/accounts/login/
curl -sk -o /dev/null -w "home:%{http_code}\n" -L --max-redirs 3 https://portal.justplay.vn/

echo "==> Done"
