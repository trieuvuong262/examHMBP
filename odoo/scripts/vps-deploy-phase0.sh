#!/usr/bin/env bash
set -Eeuo pipefail
ODOO_DIR=/opt/odoo
PORTAL_DIR=/opt/portaljustplay
cd "$ODOO_DIR"
chmod +x deploy.sh scripts/*.sh
if [[ ! -f .env ]]; then
  DB_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
  ADMIN_PASS=$(openssl rand -base64 18 | tr -d '/+=' | head -c 16)
  cp .env.example .env
  sed -i "s/^ODOO_DB_PASSWORD=.*/ODOO_DB_PASSWORD=${DB_PASS}/" .env
  sed -i "s/^ODOO_ADMIN_PASSWORD=.*/ODOO_ADMIN_PASSWORD=${ADMIN_PASS}/" .env
  echo "=== PASSWORDS (save these) ==="
  grep -E '^ODOO_(DB|ADMIN)_PASSWORD=' .env
fi
./deploy.sh
cd "$PORTAL_DIR"
docker compose -f docker-compose.yml up -d nginx
cd "$ODOO_DIR"
./scripts/setup-ssl-erp.sh
echo "=== curl tests ==="
curl -s -o /dev/null -w "odoo local %{http_code}\n" http://127.0.0.1:8069/web/database/selector || true
curl -sk -o /dev/null -w "erp https %{http_code}\n" https://erp.justplay.vn/web/database/selector || true
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'odoo|nginx|NAMES'
