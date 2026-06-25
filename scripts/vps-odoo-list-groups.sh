#!/usr/bin/env bash
docker exec -i odoo-web odoo shell -d justplay_pilot --no-http <<'PY'
for g in env["res.groups"].sudo().search([]):
    fn = g.full_name or ""
    if "Contact" in fn or "Extra" in fn or "Settings" in fn:
        print(g.id, fn)
PY
