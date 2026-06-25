#!/usr/bin/env bash
set -euo pipefail
cd /opt/odoo
set -a; source .env; set +a
CONF=config/odoo.conf
sed -i "s/^admin_passwd = .*/admin_passwd = ${ODOO_ADMIN_PASSWORD}/" "$CONF"
sed -i "s/^db_password = .*/db_password = ${ODOO_DB_PASSWORD}/" "$CONF"
sed -i "s/^db_user = .*/db_user = ${ODOO_DB_USER:-odoo}/" "$CONF"
if [[ -f .portal_sso_secret ]]; then
  SECRET=$(cat .portal_sso_secret)
  sed -i "s|^portal_sso_secret =.*|portal_sso_secret = ${SECRET}|" "$CONF"
fi
grep -E '^(db_password|portal_sso|addons_path)' "$CONF" | sed 's/password.*/password=***/'
docker compose up -d
sleep 3
docker compose run --rm odoo odoo -d justplay_pilot -i portal_justplay_sso --stop-after-init --no-http 2>&1 | tail -5
docker compose up -d odoo
