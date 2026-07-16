#!/usr/bin/env bash
set -euo pipefail
docker cp /opt/portaljustplay/kho_npl/odoo_bridge.py portaljustplay-web-1:/app/kho_npl/odoo_bridge.py

echo '=== Cleanup duplicate NPL warehouses on Odoo ==='
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http -c /etc/odoo/odoo.conf <<'PY'
whs = env['stock.warehouse'].search([('name', 'ilike', 'Nguyên Phụ Liệu')])
print('before', [(w.id, w.code, w.name) for w in whs])
keep = whs.filtered(lambda w: w.code == 'NPL')[:1] or whs[:1]
for w in whs - keep:
    # Không xóa WH có quants dễ — đổi tên + code tạm để tránh trùng
    try:
        w.write({'name': w.name + ' (cũ)', 'code': ('OLD%d' % w.id)[:5]})
        print('renamed', w.id)
    except Exception as e:
        print('skip', w.id, e)
if keep and keep.code != 'NPL':
    try:
        keep.write({'code': 'NPL', 'name': 'Kho Nguyên Phụ Liệu'})
        print('normalized keep', keep.id)
    except Exception as e:
        print('norm fail', e)
env.cr.commit()
whs2 = env['stock.warehouse'].search([])
print('all warehouses', [(w.id, w.code, w.name) for w in whs2])
PY

echo '=== Re-apply push limit 20 (idempotent) ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --apply --limit 20

echo '=== Push 4 seed materials for costing pilot ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_push --apply --codes JP-VAI-COT180-WHT --codes JP-CHI-PES40-WHT --codes JP-TEM-SIZE-JP --codes JP-TUI-OPP-30x40

echo '=== Reconcile ==='
docker exec portaljustplay-web-1 python manage.py npl_odoo_reconcile --limit 30 --show missing_in_odoo --show-limit 5

echo DONE
