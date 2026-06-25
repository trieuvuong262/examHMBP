#!/usr/bin/env bash
# Cấu hình ODOO_* trên Portal + tài khoản API đồng bộ trên Odoo.
set -euo pipefail

PORTAL_DIR="${PORTAL_DIR:-/opt/portaljustplay}"
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
ODOO_DB="${ODOO_DB:-justplay_pilot}"
ODOO_URL="${ODOO_URL:-https://erp.justplay.vn}"
API_USER="${ODOO_API_USER:-portal_sync}"

ENV_FILE="$PORTAL_DIR/.env"
API_PASS_FILE="$ODOO_DIR/.portal_api_password"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: missing $ENV_FILE" >&2
  exit 1
fi

if [[ -f "$API_PASS_FILE" ]]; then
  API_PASSWORD="$(cat "$API_PASS_FILE")"
  echo "==> Dùng lại mật khẩu API từ $API_PASS_FILE"
else
  API_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
  umask 077
  echo "$API_PASSWORD" > "$API_PASS_FILE"
  chmod 600 "$API_PASS_FILE"
  echo "==> Tạo mật khẩu API mới: $API_PASS_FILE"
fi

export API_USER API_PASSWORD ODOO_DB

echo "==> Tạo/cập nhật user Odoo: $API_USER"
docker exec -e API_USER -e API_PASSWORD -i odoo-web odoo shell -d "$ODOO_DB" --no-http <<'PY'
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
    print(f"updated user id={user.id}")
else:
    vals["password"] = password
    user = User.create(vals)
    print(f"created user id={user.id}")
env.cr.commit()
PY

upsert_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

echo "==> Ghi ODOO_* vào Portal .env"
upsert_env ODOO_URL "$ODOO_URL"
upsert_env ODOO_PUBLIC_URL "$ODOO_URL"
upsert_env ODOO_DB "$ODOO_DB"
upsert_env ODOO_API_USER "$API_USER"
upsert_env ODOO_API_PASSWORD "$API_PASSWORD"
upsert_env ODOO_VERIFY_SSL "1"
upsert_env ODOO_DEFAULT_GROUPS "base.group_user,stock.group_stock_user,mrp.group_mrp_user"
upsert_env ODOO_MANAGER_GROUPS "stock.group_stock_manager,mrp.group_mrp_manager"

echo "==> Khởi động lại Portal web (nạp .env mới)"
cd "$PORTAL_DIR"
docker compose up -d web

echo "==> Kiểm tra XML-RPC qua Django settings"
docker exec portaljustplay-web-1 python manage.py shell -c "
from django.conf import settings
import xmlrpc.client
url = settings.ODOO_URL.rstrip('/')
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(settings.ODOO_DB, settings.ODOO_API_USER, settings.ODOO_API_PASSWORD, {})
print('uid=', uid)
assert uid, 'XML-RPC auth failed'
"

echo "==> Xong. Portal đã cấu hình ODOO_API_* (user: $API_USER)"
