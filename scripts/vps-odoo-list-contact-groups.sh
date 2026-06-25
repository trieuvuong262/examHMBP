#!/usr/bin/env bash
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
groups = env["res.groups"].sudo().search([("name", "ilike", "contact")])
for g in groups:
    print(g.id, g.full_name)
PY
