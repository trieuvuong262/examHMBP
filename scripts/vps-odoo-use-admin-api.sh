#!/usr/bin/env bash
set -euo pipefail
export API_PASSWORD="$(cat /opt/odoo/.portal_api_password)"
docker exec -e API_PASSWORD -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
import os
admin = env["res.users"].sudo().search([("login", "=", "it@justplay.vn")], limit=1)
sync = env["res.users"].sudo().search([("login", "=", "portal_sync")], limit=1)
password = os.environ["API_PASSWORD"]
if admin:
    admin.write({"password": password})
    print("admin password updated", admin.id)
if sync and admin:
    sync.write({
        "groups_id": [(6, 0, admin.groups_id.ids)],
        "active": True,
        "password": password,
    })
    print("portal_sync groups copied from admin", len(admin.groups_id))
env.cr.commit()
PY

sed -i 's/^ODOO_API_USER=.*/ODOO_API_USER=it@justplay.vn/' /opt/portaljustplay/.env
cd /opt/portaljustplay && docker compose up -d web
sleep 4
bash /tmp/vps-odoo-test-create-user2.sh 2>&1 | tail -6
