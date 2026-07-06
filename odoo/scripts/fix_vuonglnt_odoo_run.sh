#!/usr/bin/env bash
# Sửa Vuonglnt không vào ERP: kích hoạt lại Odoo user + đồng bộ Portal.
set -euo pipefail

echo "==> Kích hoạt Vuonglnt trên Odoo"
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http \
  < /opt/odoo/scripts/reactivate_vuonglnt_odoo.py 2>&1 | tail -3

echo ""
echo "==> Đồng bộ Portal → Odoo"
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sync import sync_user_to_odoo
from audit.services.odoo_sso import odoo_sso_configured, build_odoo_sso_token

u = User.objects.get(username__iexact='Vuonglnt')
p = u.profile
r = sync_user_to_odoo(u)
print('sync', r)
print('profile odoo_user_id', p.odoo_user_id)
print('password_synced', p.odoo_password_synced)
print('sso_ready', bool(odoo_sso_configured() and build_odoo_sso_token(u)))
" 2>&1 | tail -10

echo ""
echo "==> Xác nhận Odoo DB"
docker exec odoo-db psql -U odoo -d justplay_pilot -c \
  "SELECT id, login, active FROM res_users WHERE login ILIKE 'vuonglnt';"
