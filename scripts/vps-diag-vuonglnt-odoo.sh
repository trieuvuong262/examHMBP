#!/usr/bin/env bash
set -euo pipefail
cd /opt/portaljustplay

docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sync import user_has_odoo_portal_access, odoo_login_url, sync_user_to_odoo
from hrm.module_permissions import MODULE_ODOO, get_user_enabled_modules
from hrm.group_permissions import get_user_module_perm

u = User.objects.select_related('profile__permission_group', 'profile__department').get(username='Vuonglnt')
p = u.profile
print('username', u.username)
print('email', repr(u.email))
print('odoo_user_id', p.odoo_user_id)
print('dept', p.department.name if p.department_id else None)
print('group', p.permission_group.name if p.permission_group_id else None)
print('odoo perm', get_user_module_perm(u, MODULE_ODOO))
print('has access', user_has_odoo_portal_access(u))
print('odoo login url', odoo_login_url(u))
r = sync_user_to_odoo(u)
print('sync', r)
"

echo "==> Odoo DB users"
docker exec odoo-db psql -U odoo -d justplay_pilot -c "SELECT id, login, active, share FROM res_users WHERE id IN (13) OR login ILIKE '%vuong%';"
