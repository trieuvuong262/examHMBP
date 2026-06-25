#!/usr/bin/env bash
set -Eeuo pipefail

# Triển khai Odoo Community — KHÔNG đụng database Portal.
#
# Lần đầu trên VPS:
#   sudo mkdir -p /opt/odoo
#   rsync -a odoo/ /opt/odoo/
#   cd /opt/odoo && cp .env.example .env && nano .env
#   chmod +x deploy.sh scripts/*.sh
#   ./deploy.sh
#   ./scripts/setup-ssl-erp.sh

ODOO_DIR="${ODOO_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$ODOO_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: Thiếu $ODOO_DIR/.env — chạy: cp .env.example .env"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

for var in ODOO_DB_PASSWORD ODOO_ADMIN_PASSWORD; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: $var trống trong .env"
    exit 1
  fi
done

compose() {
  docker compose "$@"
}

echo "==> Odoo Community (Phase 0)"
echo "    Thư mục: $ODOO_DIR"
echo "    Domain:  ${ODOO_PUBLIC_HOST:-erp.justplay.vn}"
echo "    Image:   ${ODOO_IMAGE:-odoo:18.0}"

# Đồng bộ mật khẩu vào odoo.conf (file mount read-only trong container — ghi tạm rồi mount)
CONF="$ODOO_DIR/config/odoo.conf"
sed -i "s/^admin_passwd = .*/admin_passwd = ${ODOO_ADMIN_PASSWORD}/" "$CONF"
sed -i "s/^db_password = .*/db_password = ${ODOO_DB_PASSWORD}/" "$CONF"
sed -i "s/^db_user = .*/db_user = ${ODOO_DB_USER:-odoo}/" "$CONF"
if [[ -n "${PORTAL_SSO_SECRET:-}" ]]; then
  if grep -q '^portal_sso_secret' "$CONF"; then
    sed -i "s|^portal_sso_secret =.*|portal_sso_secret = ${PORTAL_SSO_SECRET}|" "$CONF"
  else
    echo "portal_sso_secret = ${PORTAL_SSO_SECRET}" >> "$CONF"
  fi
fi

echo "==> Pull images..."
compose pull

echo "==> Khởi động PostgreSQL + Odoo..."
compose up -d

DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
for mod in portal_justplay_sso portal_justplay_brand; do
  if [[ -d "addons/${mod}" ]]; then
    echo "==> Cài addon ${mod} trên DB ${DB_NAME}..."
    compose run --rm odoo odoo -d "$DB_NAME" -i "$mod" --stop-after-init --no-http || true
  fi
done
compose up -d odoo

if [[ "${ODOO_LDAP_ENABLE:-0}" == "1" ]]; then
  echo "==> Cấu hình LDAP (auth_ldap)..."
  bash "$ODOO_DIR/scripts/configure_ldap.sh"
fi

echo "==> Trạng thái:"
compose ps

echo ""
echo "Odoo lắng nghe: 127.0.0.1:8069 (proxy qua nginx Portal)"
echo "Bước tiếp: ./scripts/setup-ssl-erp.sh  (HTTPS erp.justplay.vn)"
echo "Sau SSL: mở https://${ODOO_PUBLIC_HOST:-erp.justplay.vn}/ → tạo database pilot"
