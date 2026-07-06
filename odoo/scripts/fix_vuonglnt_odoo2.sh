#!/usr/bin/env bash
set -euo pipefail
echo "=== All res_users login like vuong (raw SQL) ==="
docker exec odoo-db psql -U odoo -d justplay_pilot -c \
  "SELECT id, login, active, share FROM res_users WHERE lower(login) LIKE '%vuong%';"

echo ""
echo "=== Duplicate logins (case-insensitive) ==="
docker exec odoo-db psql -U odoo -d justplay_pilot -c \
  "SELECT lower(login) AS l, count(*), array_agg(id ORDER BY id) AS ids, array_agg(active::text) AS actives FROM res_users GROUP BY lower(login) HAVING count(*) > 1 AND lower(login) LIKE '%vuong%';"

echo ""
echo "=== res_partner linked ==="
docker exec odoo-db psql -U odoo -d justplay_pilot -c \
  "SELECT u.id, u.login, u.active, p.name FROM res_users u JOIN res_partner p ON p.id=u.partner_id WHERE lower(u.login) LIKE '%vuong%';"
