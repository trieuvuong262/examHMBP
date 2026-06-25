#!/usr/bin/env bash
docker cp /opt/portaljustplay/audit/services/odoo_sso.py portaljustplay-web-1:/app/audit/services/odoo_sso.py
docker cp /opt/portaljustplay/audit/views_odoo.py portaljustplay-web-1:/app/audit/views_odoo.py
cd /opt/portaljustplay && docker compose up -d web
sleep 3
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sso import odoo_sso_configured, odoo_entry_url, build_odoo_sso_token
u = User.objects.get(username='Vuonglnt')
print('sso_configured', odoo_sso_configured())
print('url', odoo_entry_url(u))
"

# test SSO endpoint with curl (get token from python)
TOKEN=$(docker exec portaljustplay-web-1 python manage.py shell -c "
from django.contrib.auth.models import User
from audit.services.odoo_sso import build_odoo_sso_token
print(build_odoo_sso_token(User.objects.get(username='Vuonglnt')))
" 2>/dev/null | tail -1)
echo "==> curl SSO (expect 302 to /web)"
curl -sk -o /dev/null -w '%{http_code} %{redirect_url}\n' "https://erp.justplay.vn/portal/sso?token=${TOKEN}&redirect=/web"
