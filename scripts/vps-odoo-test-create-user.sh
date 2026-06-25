#!/usr/bin/env bash
set -euo pipefail
API_PASSWORD=$(grep ^ODOO_API_PASSWORD= /opt/portaljustplay/.env | cut -d= -f2-)
docker exec portaljustplay-web-1 python manage.py shell -c "
import xmlrpc.client
from django.conf import settings
url = settings.ODOO_URL.rstrip('/')
db, user, pw = settings.ODOO_DB, settings.ODOO_API_USER, settings.ODOO_API_PASSWORD
common = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/common', allow_none=True)
models = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/object', allow_none=True)
uid = common.authenticate(db, user, pw, {})
print('uid', uid)
try:
    new_id = models.execute_kw(db, uid, pw, 'res.users', 'create', [{
        'name': 'Test Portal Sync',
        'login': 'test_portal_sync_user',
        'email': 'test@justplay.local',
        'groups_id': [(6, 0, [])],
    }])
    print('created', new_id)
    models.execute_kw(db, uid, pw, 'res.users', 'write', [[new_id], {'active': False}])
except Exception as e:
    print('error', e)
"
