#!/usr/bin/env bash
set -euo pipefail
export API_USER="${API_USER:-portal_sync}"
export API_PASSWORD="${API_PASSWORD:-$(cat /opt/odoo/.portal_api_password)}"
docker exec -e API_USER -e API_PASSWORD -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
import os
login = os.environ["API_USER"]
password = os.environ["API_PASSWORD"]
User = env["res.users"].sudo()
group_user = env.ref("base.group_user")
group_system = env.ref("base.group_system")
group_partner = env.ref("base.group_partner_manager")
group_ids = [group_user.id, group_system.id, group_partner.id]
for xml_id in (
    "stock.group_stock_manager",
    "mrp.group_mrp_manager",
    "purchase.group_purchase_manager",
):
    try:
        group_ids.append(env.ref(xml_id).id)
    except Exception:
        pass
vals = {
    "name": "Portal Sync",
    "login": login,
    "email": "portal-sync@justplay.local",
    "active": True,
    "groups_id": [(6, 0, group_ids)],
}
user = User.search([("login", "=", login)], limit=1)
if user:
    write_vals = dict(vals)
    write_vals["password"] = password
    user.write(write_vals)
    print("updated", user.id)
else:
    vals["password"] = password
    user = User.create(vals)
    print("created", user.id)
env.cr.commit()
PY
