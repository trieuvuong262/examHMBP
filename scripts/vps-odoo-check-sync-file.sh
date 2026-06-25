#!/usr/bin/env bash
grep -n "search" /opt/portaljustplay/audit/services/odoo_sync.py | head -5
docker exec portaljustplay-web-1 grep -n "search" /app/audit/services/odoo_sync.py | head -5
