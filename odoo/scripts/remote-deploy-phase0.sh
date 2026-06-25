#!/usr/bin/env bash
# Triển khai Phase 0 Odoo lên VPS từ máy local (bash/WSL/Git Bash).
set -Eeuo pipefail

VPS_HOST="${VPS_HOST:-103.90.224.203}"
VPS_USER="${VPS_USER:-root}"
VPS_PORT="${VPS_PORT:-22}"
PORTAL_DIR="${PORTAL_DIR:-/opt/portaljustplay}"
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Copy odoo/ -> ${VPS_USER}@${VPS_HOST}:${ODOO_DIR}"
ssh -p "$VPS_PORT" "${VPS_USER}@${VPS_HOST}" "mkdir -p ${ODOO_DIR}"
rsync -az --delete \
  -e "ssh -p ${VPS_PORT}" \
  "${ROOT}/odoo/" "${VPS_USER}@${VPS_HOST}:${ODOO_DIR}/"

echo "==> Copy nginx erp configs -> Portal"
rsync -az -e "ssh -p ${VPS_PORT}" \
  "${ROOT}/PortalJustPlay/nginx/erp.conf" \
  "${ROOT}/PortalJustPlay/nginx/erp-ssl.conf" \
  "${ROOT}/PortalJustPlay/nginx/erp-redirect.conf" \
  "${VPS_USER}@${VPS_HOST}:${PORTAL_DIR}/PortalJustPlay/nginx/"

echo "==> Copy docker-compose nginx updates"
rsync -az -e "ssh -p ${VPS_PORT}" \
  "${ROOT}/docker-compose.yml" \
  "${ROOT}/docker-compose.ssl.yml" \
  "${VPS_USER}@${VPS_HOST}:${PORTAL_DIR}/"

echo "==> Remote: init .env + deploy Odoo + nginx + SSL"
ssh -p "$VPS_PORT" "${VPS_USER}@${VPS_HOST}" bash -s <<REMOTE
set -Eeuo pipefail
ODOO_DIR="${ODOO_DIR}"
PORTAL_DIR="${PORTAL_DIR}"

cd "\$ODOO_DIR"
chmod +x deploy.sh scripts/*.sh

if [[ ! -f .env ]]; then
  DB_PASS=\$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
  ADMIN_PASS=\$(openssl rand -base64 18 | tr -d '/+=' | head -c 16)
  cp .env.example .env
  sed -i "s/^ODOO_DB_PASSWORD=.*/ODOO_DB_PASSWORD=\${DB_PASS}/" .env
  sed -i "s/^ODOO_ADMIN_PASSWORD=.*/ODOO_ADMIN_PASSWORD=\${ADMIN_PASS}/" .env
  echo "==> Đã tạo .env — lưu mật khẩu:"
  grep -E '^ODOO_(DB|ADMIN)_PASSWORD=' .env
fi

./deploy.sh

cd "\$PORTAL_DIR"
# Nếu chưa có erp-ssl cert, chỉ bật HTTP proxy trước
if [[ ! -f /etc/letsencrypt/live/erp.justplay.vn/fullchain.pem ]]; then
  docker compose -f docker-compose.yml up -d nginx
  cd "\$ODOO_DIR" && ./scripts/setup-ssl-erp.sh
else
  docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d nginx
fi

echo ""
echo "==> Kiểm tra Odoo local:"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8069/web/database/selector || true
REMOTE

echo ""
echo "Xong Phase 0. Mở: https://erp.justplay.vn/"
echo "Master password: ssh vào VPS, cat ${ODOO_DIR}/.env | grep ODOO_ADMIN"
