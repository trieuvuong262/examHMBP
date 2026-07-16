#!/usr/bin/env bash
# Cài Inventory (stock) trên Odoo pilot — nền clone NPL.
set -euo pipefail
cd /opt/odoo
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"

cat > /tmp/install_stock.py <<'PY'
# flake8: noqa
env['ir.module.module'].update_list()
env.cr.commit()
for name in ('stock', 'purchase'):
    # purchase optional for vendor on product; stock is required
    if name == 'purchase':
        # keep lean: stock only for P1; vendor via product.supplierinfo needs purchase
        pass
mod = env['ir.module.module'].search([('name', '=', 'stock')], limit=1)
if not mod:
    print('MISSING stock')
else:
    print('stock state=', mod.state)
    if mod.state != 'installed':
        print('INSTALL stock')
        mod.button_immediate_install()
        env.cr.commit()
        print('OK stock')
    else:
        print('ALREADY stock')

# product.supplierinfo lives in purchase; install purchase for vendor lines
pmod = env['ir.module.module'].search([('name', '=', 'purchase')], limit=1)
if pmod and pmod.state != 'installed':
    print('INSTALL purchase (vendor pricelist)')
    pmod.button_immediate_install()
    env.cr.commit()
    print('OK purchase')
elif pmod:
    print('ALREADY purchase')

apps = env['ir.module.module'].search([('state', '=', 'installed'), ('application', '=', True)])
print('APPS', sorted(apps.mapped('name')))
print('COUNT', env['ir.module.module'].search_count([('state', '=', 'installed')]))
PY

docker exec -i odoo-web odoo shell -d "$DB_NAME" --no-http -c /etc/odoo/odoo.conf < /tmp/install_stock.py
docker restart odoo-web
sleep 5
echo DONE
