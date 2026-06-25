#!/usr/bin/env bash
docker exec portaljustplay-web-1 python -c "from audit.services.odoo_sync import odoo_configured; print('configured', odoo_configured())" 2>&1 || echo "odoo_sync module not deployed"
docker exec portaljustplay-web-1 python manage.py showmigrations hrm 2>&1 | tail -8
