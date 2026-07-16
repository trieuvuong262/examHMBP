#!/usr/bin/env bash
# Deploy bridge NPL (đã mở rộng Supplier) + full push Portal → Odoo.
set -euo pipefail
ROOT=/opt/portaljustplay
cd "$ROOT"

echo '=== Sync bridge files from deploy host path (if present) ==='
# Files are expected already under $ROOT via scp from workstation before this script.

echo '=== Ensure Odoo API env ==='
TS=$(date +%Y%m%d%H%M%S)
cp -a .env ".env.bak.npl-full.${TS}"
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

echo '=== Recreate portal web (pick up .env) ==='
COMPOSE_BAKE=false docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d web
sleep 12

echo '=== docker cp bridge into container ==='
docker cp "$ROOT/kho_npl/odoo_bridge.py" portaljustplay-web-1:/app/kho_npl/odoo_bridge.py
docker cp "$ROOT/kho_npl/management/commands/npl_odoo_reconcile.py" portaljustplay-web-1:/app/kho_npl/management/commands/npl_odoo_reconcile.py
docker cp "$ROOT/kho_npl/management/commands/npl_odoo_push.py" portaljustplay-web-1:/app/kho_npl/management/commands/npl_odoo_push.py

echo '=== Dry-run (full, no limit) ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push

echo '=== Apply full push ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --apply

echo '=== Reconcile ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_reconcile --show missing_in_odoo --show-limit 30

echo '=== DONE full NPL push ==='
