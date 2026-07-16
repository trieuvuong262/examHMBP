#!/usr/bin/env bash
set -euo pipefail
# Re-copy fixed bridge + test push on VPS
docker cp /opt/portaljustplay/kho_npl/odoo_bridge.py portaljustplay-web-1:/app/kho_npl/odoo_bridge.py
docker cp /opt/portaljustplay/kho_npl/management/commands/npl_odoo_reconcile.py portaljustplay-web-1:/app/kho_npl/management/commands/npl_odoo_reconcile.py
docker cp /opt/portaljustplay/kho_npl/management/commands/npl_odoo_push.py portaljustplay-web-1:/app/kho_npl/management/commands/npl_odoo_push.py

echo '=== Dry-run limit 20 ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --limit 20

echo '=== Apply limit 20 ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --apply --limit 20

echo '=== Reconcile limit 50 ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_reconcile --limit 50

echo '=== Verify on Odoo (sample products Kho NPL) ==='
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http -c /etc/odoo/odoo.conf <<'PY'
Product = env['product.product']
wh = env['stock.warehouse'].search([('code', '=', 'KHO-NPL')], limit=1)
print('warehouse', wh.name if wh else None, wh.code if wh else None)
categ = env['product.category'].search([('name', '=', 'Kho NPL')], limit=1)
print('category root', categ.id if categ else None)
npl = Product.search([('categ_id', 'child_of', categ.id)], limit=10) if categ else Product.browse()
print('npl products sample', [(p.default_code, p.name, p.qty_available) for p in npl])
print('npl count under Kho NPL', Product.search_count([('categ_id', 'child_of', categ.id)]) if categ else 0)
PY
echo DONE
