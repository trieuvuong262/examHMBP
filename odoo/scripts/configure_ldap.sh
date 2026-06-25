#!/usr/bin/env bash
# Cấu hình Odoo auth_ldap → Synology Directory Server (NAS).
# Chạy từ /opt/odoo sau khi source .env:
#   ./scripts/configure_ldap.sh
set -Eeuo pipefail

ODOO_DIR="${ODOO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ODOO_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: Thiếu $ODOO_DIR/.env"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
LDAP_SERVER="${ODOO_LDAP_SERVER:-100.93.5.42}"
LDAP_PORT="${ODOO_LDAP_PORT:-389}"
LDAP_TLS="${ODOO_LDAP_TLS:-0}"
LDAP_BASE="${ODOO_LDAP_BASE_DN:-dc=ldap,dc=justplay,dc=local}"
LDAP_BIND_DN="${ODOO_LDAP_BIND_DN:-uid=root,cn=users,dc=ldap,dc=justplay,dc=local}"
LDAP_BIND_PASSWORD="${ODOO_LDAP_BIND_PASSWORD:-}"
LDAP_FILTER="${ODOO_LDAP_FILTER:-(uid=%s)}"
LDAP_CREATE_USER="${ODOO_LDAP_CREATE_USER:-1}"

if [[ -z "$LDAP_BIND_PASSWORD" ]]; then
  echo "ERROR: ODOO_LDAP_BIND_PASSWORD trống trong .env"
  exit 1
fi

compose() {
  docker compose "$@"
}

echo "==> Cài module auth_ldap trên DB ${DB_NAME}..."
compose run --rm odoo odoo -d "$DB_NAME" -i auth_ldap --stop-after-init --no-http

echo "==> Ghi cấu hình LDAP..."
compose run --rm \
  -e ODOO_LDAP_SERVER="$LDAP_SERVER" \
  -e ODOO_LDAP_PORT="$LDAP_PORT" \
  -e ODOO_LDAP_TLS="$LDAP_TLS" \
  -e ODOO_LDAP_BASE="$LDAP_BASE" \
  -e ODOO_LDAP_BIND_DN="$LDAP_BIND_DN" \
  -e ODOO_LDAP_BIND_PASSWORD="$LDAP_BIND_PASSWORD" \
  -e ODOO_LDAP_FILTER="$LDAP_FILTER" \
  -e ODOO_LDAP_CREATE_USER="$LDAP_CREATE_USER" \
  odoo odoo shell -d "$DB_NAME" --no-http <<'PY'
import os

server = os.environ['ODOO_LDAP_SERVER']
port = int(os.environ['ODOO_LDAP_PORT'])
use_tls = os.environ['ODOO_LDAP_TLS'] in ('1', 'true', 'True', 'yes')
base = os.environ['ODOO_LDAP_BASE']
bind_dn = os.environ['ODOO_LDAP_BIND_DN']
bind_pw = os.environ['ODOO_LDAP_BIND_PASSWORD']
ldap_filter = os.environ['ODOO_LDAP_FILTER']
create_user = os.environ['ODOO_LDAP_CREATE_USER'] in ('1', 'true', 'True', 'yes')

company = env.company
Ldap = env['res.company.ldap'].sudo()
Users = env['res.users'].sudo()

template = Users.search([('login', '=', 'ldap_template')], limit=1)
if not template:
    group_ids = []
    for xml_id in ('base.group_user', 'stock.group_stock_user', 'mrp.group_mrp_user'):
        rec = env.ref(xml_id, raise_if_not_found=False)
        if rec:
            group_ids.append(rec.id)
    template = Users.create({
        'name': 'LDAP Template',
        'login': 'ldap_template',
        'active': False,
        'groups_id': [(6, 0, group_ids)] if group_ids else False,
    })
    print('Created ldap_template user id', template.id)
else:
    print('Using ldap_template user id', template.id)

vals = {
    'company': company.id,
    'ldap_server': server,
    'ldap_server_port': port,
    'ldap_binddn': bind_dn,
    'ldap_password': bind_pw,
    'ldap_filter': ldap_filter,
    'ldap_base': base,
    'ldap_tls': use_tls,
    'create_user': create_user,
    'user': template.id,
    'sequence': 10,
}
existing = Ldap.search([('company', '=', company.id)], limit=1)
if existing:
    existing.write(vals)
    rec = existing
    print('Updated LDAP config id', rec.id)
else:
    rec = Ldap.create(vals)
    print('Created LDAP config id', rec.id)

# Kiểm tra query LDAP (bind + search) qua Odoo API nội bộ
conf = rec._get_ldap_dicts()[0]
results = rec._query(conf, ldap_filter.replace('%s', 'DNhu'), ['uid', 'cn'])
print('LDAP search test DNhu:', len(results), 'hit(s)')
if not results:
    raise SystemExit('LDAP search test failed — kiểm tra bind DN / base / filter')
PY

compose up -d odoo

echo "==> Khởi động lại Odoo..."
compose restart odoo

echo "Done. Đăng nhập thử: https://${ODOO_PUBLIC_HOST:-erp.justplay.vn}/web/login (username Portal + mật khẩu LDAP)"
