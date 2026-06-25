#!/usr/bin/env bash
# Chuyển quản trị Odoo: it@justplay.vn -> admin + cập nhật Portal API.
set -euo pipefail
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
PORTAL_DIR="${PORTAL_DIR:-/opt/portaljustplay}"
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
API_PASSWORD="${API_PASSWORD:-$(cat "$ODOO_DIR/.portal_api_password")}"

cd "$ODOO_DIR"
export ADMIN_PASSWORD="$API_PASSWORD"
docker compose exec -T -e ADMIN_PASSWORD odoo \
  odoo shell -d "$DB_NAME" --no-http -c /etc/odoo/odoo.conf \
  < "$ODOO_DIR/scripts/migrate_admin_login_to_admin.py"

if grep -q '^ODOO_API_USER=' "$PORTAL_DIR/.env"; then
  sed -i 's/^ODOO_API_USER=.*/ODOO_API_USER=admin/' "$PORTAL_DIR/.env"
else
  echo 'ODOO_API_USER=admin' >> "$PORTAL_DIR/.env"
fi

cd "$PORTAL_DIR"
docker compose up -d web
sleep 3

echo "==> Odoo admin login: admin"
echo "==> Portal ODOO_API_USER=admin"
echo "==> Kiểm tra: bash $PORTAL_DIR/scripts/vps-odoo-list-users.sh"
