#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay

cp .env ".env.bak.$(date +%Y%m%d_%H%M%S)"

# Docker Compose .env: $var bị interpolate — escape $ thành $$
if grep -q '\$gvb' .env; then
  sed -i 's/\$gvb/$$gvb/g' .env
  echo "Fixed SECRET_KEY: escaped \$gvb -> \$\$gvb"
fi

grep -q '^PORTAL_DOMAIN=' .env || echo 'PORTAL_DOMAIN=portal.justplay.vn' >> .env
sed -i 's/^ALLOWED_HOSTS=.*/ALLOWED_HOSTS=103.90.224.203,portal.justplay.vn,127.0.0.1,localhost/' .env

if grep -q '^CSRF_TRUSTED_ORIGINS=' .env; then
  sed -i 's|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=http://103.90.224.203,https://103.90.224.203,http://portal.justplay.vn,https://portal.justplay.vn|' .env
else
  echo 'CSRF_TRUSTED_ORIGINS=http://103.90.224.203,https://103.90.224.203,http://portal.justplay.vn,https://portal.justplay.vn' >> .env
fi

echo "Restarting web..."
docker compose up -d web

echo "Verify (no gvb warning expected):"
docker compose exec -T web python manage.py shell <<'PY'
import os
from django.conf import settings
ek = os.environ.get("SECRET_KEY", "")
print("ENV_SECRET_LEN", len(ek))
print("ENV_HAS_gvb", "gvb" in ek)
print("CSRF_TRUSTED_ORIGINS", settings.CSRF_TRUSTED_ORIGINS)
PY
