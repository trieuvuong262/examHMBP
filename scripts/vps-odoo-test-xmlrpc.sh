#!/usr/bin/env bash
set -euo pipefail
echo "==> Odoo users portal_sync"
docker exec odoo-db psql -U odoo -d justplay_pilot -tAc "SELECT id, login, active FROM res_users WHERE login LIKE '%portal%' OR login LIKE '%sync%';"

echo "==> Portal .env ODOO (masked)"
grep '^ODOO_' /opt/portaljustplay/.env | sed 's/PASSWORD=.*/PASSWORD=***/'

echo "==> XML-RPC from host (public URL)"
python3 - <<'PY'
import xmlrpc.client
url = 'https://erp.justplay.vn'
db = 'justplay_pilot'
user = 'portal_sync'
import subprocess
password = subprocess.check_output(['bash', '-c', 'grep ^ODOO_API_PASSWORD= /opt/portaljustplay/.env | cut -d= -f2-']).decode().strip()
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
print('version', common.version())
uid = common.authenticate(db, user, password, {})
print('public uid', uid)
PY

echo "==> XML-RPC from portal container"
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.conf import settings
import xmlrpc.client
print('ODOO_URL', settings.ODOO_URL)
print('ODOO_DB', settings.ODOO_DB)
print('ODOO_API_USER', settings.ODOO_API_USER)
print('pass len', len(settings.ODOO_API_PASSWORD or ''))
common = xmlrpc.client.ServerProxy(settings.ODOO_URL.rstrip('/') + '/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(settings.ODOO_DB, settings.ODOO_API_USER, settings.ODOO_API_PASSWORD, {})
print('container uid', uid)
"

echo "==> XML-RPC internal odoo-web:8069"
python3 - <<'PY'
import xmlrpc.client, subprocess
password = subprocess.check_output(['bash', '-c', 'grep ^ODOO_API_PASSWORD= /opt/portaljustplay/.env | cut -d= -f2-']).decode().strip()
common = xmlrpc.client.ServerProxy('http://127.0.0.1:8069/xmlrpc/2/common', allow_none=True)
uid = common.authenticate('justplay_pilot', 'portal_sync', password, {})
print('localhost uid', uid)
PY
