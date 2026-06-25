#!/usr/bin/env bash
set -Eeuo pipefail

# SSL Let's Encrypt cho erp.justplay.vn — dùng chung certbot webroot của Portal.

ODOO_DIR="${ODOO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ODOO_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: Thiếu .env"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

DOMAIN="${ODOO_PUBLIC_HOST:-erp.justplay.vn}"
EMAIL="${SSL_EMAIL:-}"
PORTAL_DIR="${PORTAL_PROJECT_DIR:-/opt/portaljustplay}"

if [[ -z "$EMAIL" ]]; then
  echo "ERROR: Set SSL_EMAIL trong odoo/.env"
  exit 1
fi

if [[ ! -d "$PORTAL_DIR" ]]; then
  echo "ERROR: Không thấy Portal tại $PORTAL_DIR"
  exit 1
fi

echo "==> 1) Nginx Portal (HTTP; chưa bật erp-ssl nếu chưa có cert)"
cd "$PORTAL_DIR"
if [[ -f /etc/letsencrypt/live/${DOMAIN}/fullchain.pem ]]; then
  docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d nginx
else
  docker compose -f docker-compose.yml up -d nginx
fi

CERTBOT_VOL="$(docker volume ls -q | grep certbot_webroot | head -1 || true)"
if [[ -z "$CERTBOT_VOL" ]]; then
  echo "ERROR: Không tìm thấy volume certbot_webroot"
  exit 1
fi

echo "==> 2) Certbot cho $DOMAIN"
docker run --rm \
  -v "${CERTBOT_VOL}:/var/www/certbot" \
  -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive

ERP_SSL="$PORTAL_DIR/PortalJustPlay/nginx/erp-ssl.conf"
if [[ ! -f "$ERP_SSL" ]]; then
  echo "ERROR: Thiếu $ERP_SSL — git pull Portal hoặc copy nginx config"
  exit 1
fi

echo "==> 3) Bật HTTPS erp + redirect HTTP"
ERP_REDIRECT="$PORTAL_DIR/PortalJustPlay/nginx/erp-redirect.conf"
if [[ -f "$ERP_REDIRECT" ]]; then
  cp "$ERP_REDIRECT" "$PORTAL_DIR/PortalJustPlay/nginx/erp.conf"
fi

cd "$PORTAL_DIR"
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d nginx

echo ""
echo "SSL erp xong: https://${DOMAIN}/"
