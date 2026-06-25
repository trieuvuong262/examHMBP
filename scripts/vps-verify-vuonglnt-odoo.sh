#!/usr/bin/env bash
docker exec portaljustplay-web-1 python manage.py shell -c "
import xmlrpc.client
from django.conf import settings
from django.contrib.auth.models import User
from audit.services.odoo_sync import user_has_odoo_portal_access

u = User.objects.get(username='Vuonglnt')
p = u.profile
print('has_access', user_has_odoo_portal_access(u))
print('password_synced', p.odoo_password_synced)
print('odoo_user_id', p.odoo_user_id)

# verify with known password from env file - skip, just check flag
common = xmlrpc.client.ServerProxy(settings.ODOO_URL.rstrip('/') + '/xmlrpc/2/common', allow_none=True)
# auth test done during notify - if password_synced True, sync succeeded
print('ready', p.odoo_password_synced and p.odoo_user_id)
"
