#!/usr/bin/env bash
docker exec portaljustplay-web-1 python manage.py shell -c "
import xmlrpc.client
from django.conf import settings
url = settings.ODOO_URL.rstrip('/')
db = settings.ODOO_DB
common = xmlrpc.client.ServerProxy(url + '/xmlrpc/2/common', allow_none=True)
for login in ['Vuonglnt', 'vuonglnt', 'VUONGLNT']:
    for pw in ['wrongpass', 'test']:
        uid = common.authenticate(db, login, pw, {})
        print(repr(login), repr(pw), '->', uid)
"
