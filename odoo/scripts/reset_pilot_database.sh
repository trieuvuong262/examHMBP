#!/usr/bin/env bash
# Reset Odoo pilot DB — empty slate for redesign.
set -euo pipefail
cd /opt/odoo
set -a
# shellcheck disable=SC1091
source .env
set +a

DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
ADMIN_PASS="${ODOO_RESET_ADMIN_PASSWORD:-123123sS@@}"
ADMIN_LOGIN=admin
DB_PASS="${ODOO_DB_PASSWORD:?missing ODOO_DB_PASSWORD}"

echo "==> Stop odoo-web"
docker compose stop odoo

echo "==> Drop + recreate ${DB_NAME}"
docker exec -e PGPASSWORD="$DB_PASS" odoo-db psql -U odoo -d postgres -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null
docker exec -e PGPASSWORD="$DB_PASS" odoo-db psql -U odoo -d postgres -v ON_ERROR_STOP=1 -c \
  "DROP DATABASE IF EXISTS ${DB_NAME};"
docker exec -e PGPASSWORD="$DB_PASS" odoo-db psql -U odoo -d postgres -v ON_ERROR_STOP=1 -c \
  "CREATE DATABASE ${DB_NAME} OWNER odoo ENCODING 'UTF8' TEMPLATE template0;"

# Patch conf from .env
CONF=config/odoo.conf
cp -a "$CONF" "${CONF}.bak.reset"
python3 - <<'PY'
import os, re
path = "config/odoo.conf"
db_pass = os.environ["ODOO_DB_PASSWORD"]
admin = os.environ.get("ODOO_ADMIN_PASSWORD", "")
text = open(path, encoding="utf-8").read()
text = re.sub(r"(?m)^db_password = .*", "db_password = " + db_pass, text)
if admin:
    text = re.sub(r"(?m)^admin_passwd = .*", "admin_passwd = " + admin, text)
open(path, "w", encoding="utf-8").write(text)
print("conf patched")
PY

echo "==> Init base via compose run (no port conflict)"
docker compose run --rm --no-deps odoo odoo \
  -d "${DB_NAME}" \
  -i base \
  --stop-after-init \
  --without-demo=all \
  -c /etc/odoo/odoo.conf \
  2>&1 | tail -60

echo "==> Start odoo-web for shell config"
docker compose start odoo
sleep 12

echo "==> Configure admin"
cat > /tmp/set_admin_fresh.py <<EOF
admin = env['res.users'].browse(env.ref('base.user_admin').id)
admin.sudo().write({
    'login': '${ADMIN_LOGIN}',
    'password': '${ADMIN_PASS}',
    'name': 'Administrator',
})
try:
    lang = env.ref('base.lang_vi_VN')
    wiz = env['base.language.install'].create({'lang_ids': [(4, lang.id)]})
    wiz.lang_install()
    admin.sudo().write({'lang': 'vi_VN'})
except Exception as e:
    print('lang skip', e)
env.company.write({'name': 'JustPlay'})
env.cr.commit()
print('OK admin')
apps = env['ir.module.module'].search([('state', '=', 'installed'), ('application', '=', True)])
print('APPS', sorted(apps.mapped('name')))
print('INSTALLED', env['ir.module.module'].search_count([('state', '=', 'installed')]))
EOF
docker exec -i odoo-web odoo shell -d "${DB_NAME}" --no-http -c /etc/odoo/odoo.conf < /tmp/set_admin_fresh.py 2>&1 | tail -25

echo "==> Install JustPlay addons"
cat > /tmp/install_jp_addons.py <<'EOF'
env['ir.module.module'].update_list()
env.cr.commit()
for name in ('portal_justplay_sso', 'portal_justplay_brand'):
    mod = env['ir.module.module'].search([('name', '=', name)], limit=1)
    if not mod:
        print('MISSING', name)
        continue
    if mod.state != 'installed':
        print('INSTALL', name)
        mod.button_immediate_install()
        env.cr.commit()
        print('OK', name)
    else:
        print('ALREADY', name)
apps = env['ir.module.module'].search([('state', '=', 'installed'), ('application', '=', True)])
print('FINAL_APPS', sorted(apps.mapped('name')))
print('FINAL_COUNT', env['ir.module.module'].search_count([('state', '=', 'installed')]))
EOF
docker exec -i odoo-web odoo shell -d "${DB_NAME}" --no-http -c /etc/odoo/odoo.conf < /tmp/install_jp_addons.py 2>&1 | tail -40

docker restart odoo-web
sleep 6
echo "==> DONE — empty ERP"
echo "    login: ${ADMIN_LOGIN} / ${ADMIN_PASS}"
echo "    url: https://erp.justplay.vn/"
echo "    cleared: stock/mrp/purchase/sales/crm/pos/demo/NPL push data"
