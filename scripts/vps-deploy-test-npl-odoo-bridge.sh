#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay
TS=$(date +%Y%m%d%H%M%S)
cp -a .env ".env.bak.npl-bridge.${TS}"

# Ensure API credentials match Odoo admin
if grep -q '^ODOO_API_USER=' .env; then
  sed -i 's/^ODOO_API_USER=.*/ODOO_API_USER=admin/' .env
else
  echo 'ODOO_API_USER=admin' >> .env
fi
if grep -q '^ODOO_API_PASSWORD=' .env; then
  sed -i 's/^ODOO_API_PASSWORD=.*/ODOO_API_PASSWORD=123123sS@@/' .env
else
  echo 'ODOO_API_PASSWORD=123123sS@@' >> .env
fi

echo '=== Odoo env (masked) ==='
grep -E '^ODOO_(URL|DB|API_USER|API_PASSWORD)=' .env | sed 's/PASSWORD=.*/PASSWORD=***/'

echo '=== Recreate portal web ==='
COMPOSE_BAKE=false docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d web
sleep 10

echo '=== Copy bridge into container ==='
docker cp /opt/portaljustplay/kho_npl/odoo_bridge.py portaljustplay-web-1:/app/kho_npl/odoo_bridge.py
docker cp /opt/portaljustplay/kho_npl/management/commands/npl_odoo_reconcile.py portaljustplay-web-1:/app/kho_npl/management/commands/npl_odoo_reconcile.py
docker cp /opt/portaljustplay/kho_npl/management/commands/npl_odoo_push.py portaljustplay-web-1:/app/kho_npl/management/commands/npl_odoo_push.py
docker exec portaljustplay-web-1 ls -la /app/kho_npl/odoo_bridge.py /app/kho_npl/management/commands/npl_odoo_reconcile.py /app/kho_npl/management/commands/npl_odoo_push.py

echo '=== Dry-run push (limit 20) ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --limit 20

echo '=== Apply push (limit 20) ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --apply --limit 20

echo '=== Reconcile ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_reconcile --limit 50

echo '=== DONE ==='
