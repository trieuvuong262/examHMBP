#!/usr/bin/env bash
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
u = env["res.users"].sudo().search([("login", "=", "portal_sync")], limit=1)
print("user", u.id, u.login)
for g in u.groups_id:
    print("-", g.id, g.full_name)
PY
