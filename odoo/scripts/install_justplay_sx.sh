#!/usr/bin/env bash
# Cài mrp (nếu thiếu) + justplay_sx trên justplay_pilot
set -euo pipefail
cd /opt/odoo
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"

cat > /tmp/install_justplay_sx.py <<'PY'
env['ir.module.module'].update_list()
env.cr.commit()
for name in ('mrp', 'justplay_sx'):
    mod = env['ir.module.module'].search([('name', '=', name)], limit=1)
    if not mod:
        print('MISSING', name)
        continue
    print(name, 'state=', mod.state)
    if mod.state != 'installed':
        print('INSTALL', name)
        mod.button_immediate_install()
        env.cr.commit()
        print('OK', name)
    else:
        print('ALREADY', name)
        if name == 'justplay_sx':
            print('UPGRADE', name)
            mod.button_immediate_upgrade()
            env.cr.commit()

menus = env['ir.ui.menu'].search([('name', 'ilike', 'Sản xuất JustPlay')])
print('MENUS', menus.mapped('name'), 'children', len(menus.child_id) if menus else 0)
print('SO', env['justplay.sx.sale.order'].search_count([]))
print('PLAN', env['justplay.sx.plan'].search_count([]))
print('APPS', sorted(env['ir.module.module'].search([('state', '=', 'installed'), ('application', '=', True)]).mapped('name')))
PY

docker exec -i odoo-web odoo shell -d "$DB_NAME" --no-http -c /etc/odoo/odoo.conf < /tmp/install_justplay_sx.py
docker restart odoo-web
sleep 5
echo DONE
