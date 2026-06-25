#!/usr/bin/env bash
# Bật SSO Portal ↔ Odoo: secret chung + cài addon.
set -euo pipefail

PORTAL_DIR="${PORTAL_DIR:-/opt/portaljustplay}"
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"

if [[ -f "$ODOO_DIR/.portal_sso_secret" ]]; then
  SECRET="$(cat "$ODOO_DIR/.portal_sso_secret")"
  echo "==> Dùng lại secret từ $ODOO_DIR/.portal_sso_secret"
else
  SECRET="$(openssl rand -base64 48 | tr -d '/+=' | head -c 64)"
  umask 077
  echo "$SECRET" > "$ODOO_DIR/.portal_sso_secret"
  chmod 600 "$ODOO_DIR/.portal_sso_secret"
  echo "==> Tạo secret mới: $ODOO_DIR/.portal_sso_secret"
fi

upsert_env() {
  local file="$1" key="$2" val="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$file"
  else
    echo "${key}=${val}" >> "$file"
  fi
}

echo "==> Portal .env"
upsert_env "$PORTAL_DIR/.env" ODOO_SSO_SECRET "$SECRET"
upsert_env "$PORTAL_DIR/.env" ODOO_SSO_TTL_SECONDS "120"

echo "==> Odoo .env + odoo.conf"
upsert_env "$ODOO_DIR/.env" PORTAL_SSO_SECRET "$SECRET"
CONF="$ODOO_DIR/config/odoo.conf"
if grep -q '^portal_sso_secret' "$CONF"; then
  sed -i "s|^portal_sso_secret =.*|portal_sso_secret = ${SECRET}|" "$CONF"
else
  echo "portal_sso_secret = ${SECRET}" >> "$CONF"
fi

echo "==> Deploy addon mount + install module"
cd "$ODOO_DIR"
docker compose up -d
docker compose run --rm odoo odoo -d "$DB_NAME" -i portal_justplay_sso --stop-after-init --no-http
docker compose up -d odoo

cd "$PORTAL_DIR"
docker compose up -d web

echo "==> Kiểm tra SSO URL"
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sso import odoo_sso_configured, odoo_entry_url
u = User.objects.filter(profile__odoo_user_id__isnull=False).first()
print('sso_configured', odoo_sso_configured())
if u:
    print('sample_url', odoo_entry_url(u)[:80], '...')
"

echo "==> Xong SSO"
