#!/usr/bin/env bash
docker exec portaljustplay-web-1 python manage.py shell -c "
import xmlrpc.client
from django.conf import settings
url = settings.ODOO_URL.rstrip('/')
db, user, pw = settings.ODOO_DB, settings.ODOO_API_USER, settings.ODOO_API_PASSWORD
models = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/object', allow_none=True)
common = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(db, user, pw, {})
for test in [
    {'name': 'Test A', 'login': 'test_portal_a', 'email': 'a@t.local', 'groups_id': [(6, 0, [1])]},
    {'name': 'Test B', 'login': 'test_portal_b', 'email': 'b@t.local'},
]:
    try:
        new_id = models.execute_kw(db, uid, pw, 'res.users', 'create', [test])
        print('ok', test['login'], new_id)
        models.execute_kw(db, uid, pw, 'res.users', 'unlink', [[new_id]])
    except Exception as e:
        print('fail', test['login'], str(e)[:120])
"
