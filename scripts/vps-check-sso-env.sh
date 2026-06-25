#!/usr/bin/env bash
grep ODOO_SSO /opt/portaljustplay/.env | sed 's/SECRET=.*/SECRET=***/'
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.conf import settings
from audit.services.odoo_sso import odoo_sso_configured
from audit.services.odoo_sync import odoo_configured
print('ODOO_SSO_SECRET len', len(getattr(settings, 'ODOO_SSO_SECRET', '') or ''))
print('odoo_configured', odoo_configured())
print('sso_configured', odoo_sso_configured())
"
