#!/usr/bin/env bash
set -euo pipefail
docker exec portaljustplay-web-1 python manage.py shell -c "
from audit.services.odoo_sync import odoo_configured
print('configured', odoo_configured())
"
docker exec portaljustplay-web-1 python manage.py sync_odoo_users 2>&1 | tail -20
