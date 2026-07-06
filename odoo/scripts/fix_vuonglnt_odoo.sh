#!/usr/bin/env bash
# Chẩn đoán + sửa Vuonglnt ↔ Odoo (trùng login).
set -euo pipefail

echo "=== Odoo users (vuong) ==="
docker exec odoo-db psql -U odoo -d justplay_pilot -c \
  "SELECT id, login, active, share FROM res_users WHERE login ILIKE '%vuong%' ORDER BY id;"

echo ""
echo "=== Portal Vuonglnt ==="
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sync import user_has_odoo_portal_access, sync_user_to_odoo, _execute

u = User.objects.get(username__iexact='Vuonglnt')
p = u.profile
print('username', u.username)
print('odoo_user_id', p.odoo_user_id)
print('password_synced', p.odoo_password_synced)
print('has_odoo_access', user_has_odoo_portal_access(u))

# Tìm mọi res.users trùng login (case-insensitive)
login = u.username.strip()
hits = _execute('res.users', 'search_read', [('login', '=ilike', login)], fields=['id', 'login', 'active', 'share'])
print('odoo_hits', hits)
"
