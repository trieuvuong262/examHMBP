#!/bin/bash
set -euo pipefail

echo "=== Portal ductn ==="
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sync import _portal_login, sync_user_to_odoo
u = User.objects.get(username__iexact='ductn')
p = u.profile
print('username=', u.username)
print('portal_login=', _portal_login(u))
print('odoo_user_id=', p.odoo_user_id)
"

echo ""
echo "=== Odoo Ductn groups before upgrade ==="
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
ductn = env['res.users'].sudo().search([('login', 'in', ['Ductn', 'ductn'])])
for u in ductn:
    print(f'id={u.id} login={u.login!r} groups={len(u.groups_id)} system={u.has_group("base.group_system")}')
PY

echo ""
echo "=== Upgrade Ductn to admin groups ==="
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http < /opt/odoo/scripts/upgrade_ductn_odoo_admin.py

echo ""
echo "=== Restart Odoo (clear sessions) ==="
docker restart odoo-web
sleep 8

echo ""
echo "=== Odoo Ductn after restart ==="
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
ductn = env['res.users'].sudo().search([('login', 'in', ['Ductn', 'ductn'])], limit=1)
admin = env['res.users'].sudo().search([('login', '=', 'admin')], limit=1)
print(f'ductn login={ductn.login!r} groups={len(ductn.groups_id)} system={ductn.has_group("base.group_system")}')
print(f'admin groups={len(admin.groups_id)}')
missing = set(admin.groups_id.ids) - set(ductn.groups_id.ids)
extra = set(ductn.groups_id.ids) - set(admin.groups_id.ids)
print(f'missing vs admin: {len(missing)} extra: {len(extra)}')
PY

echo "DONE"
