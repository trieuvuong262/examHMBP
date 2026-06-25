#!/usr/bin/env bash
# Cài / cập nhật theme JustPlay trên Odoo.
set -euo pipefail
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
cd "$ODOO_DIR"
set -a; source .env; set +a
CONF=config/odoo.conf
sed -i "s/^admin_passwd = .*/admin_passwd = ${ODOO_ADMIN_PASSWORD}/" "$CONF"
sed -i "s/^db_password = .*/db_password = ${ODOO_DB_PASSWORD}/" "$CONF"
if [[ -f .portal_sso_secret ]]; then
  SECRET=$(cat .portal_sso_secret)
  sed -i "s|^portal_sso_secret =.*|portal_sso_secret = ${SECRET}|" "$CONF"
fi
docker compose up -d
docker compose run --rm odoo odoo -d "$DB_NAME" -u portal_justplay_brand --stop-after-init --no-http
docker compose run --rm odoo odoo -d "$DB_NAME" -i portal_justplay_brand --stop-after-init --no-http 2>/dev/null || true
docker compose exec odoo odoo -d "$DB_NAME" --dev=assets --stop-after-init 2>/dev/null || true
docker compose up -d odoo
echo "==> Brand module OK — mở https://erp.justplay.vn/ và hard refresh (Ctrl+F5)"
