#!/usr/bin/env bash
set -Eeuo pipefail

# Cài SSL Let's Encrypt cho portal.justplay.vn trên VPS.
#
# Yêu cầu:
#   - DNS portal.justplay.vn trỏ đúng IP VPS
#   - Port 80 mở ra internet
#   - Chạy trong thư mục project (mặc định /opt/portaljustplay)
#
# Usage:
#   chmod +x scripts/setup-ssl.sh
#   SSL_EMAIL=admin@justplay.vn ./scripts/setup-ssl.sh

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DOMAIN="${PORTAL_DOMAIN:-portal.justplay.vn}"
EMAIL="${SSL_EMAIL:-}"

cd "${PROJECT_DIR}"

if [[ -z "${EMAIL}" ]]; then
  echo "ERROR: Set SSL_EMAIL, e.g. SSL_EMAIL=admin@justplay.vn ./scripts/setup-ssl.sh"
  exit 1
fi

if [[ ! -f "docker-compose.yml" ]]; then
  echo "ERROR: docker-compose.yml not found in ${PROJECT_DIR}"
  exit 1
fi

compose() {
  docker compose -f docker-compose.yml "$@"
}

compose_ssl() {
  docker compose -f docker-compose.yml -f docker-compose.ssl.yml "$@"
}

echo "==> 1) Start nginx (HTTP + webroot cho certbot)"
compose up -d nginx

echo "==> 2) Request certificate for ${DOMAIN}"
CERTBOT_VOL="$(docker volume ls -q | grep certbot_webroot | head -1 || true)"
if [[ -z "${CERTBOT_VOL}" ]]; then
  echo "ERROR: certbot_webroot volume not found. Check docker compose project name."
  exit 1
fi

docker run --rm \
  -v "${CERTBOT_VOL}:/var/www/certbot" \
  -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot certonly \
  --webroot -w /var/www/certbot \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive

echo "==> 3) Enable nginx SSL config"
SSL_CONF="PortalJustPlay/nginx/ssl.conf"
if [[ ! -f "${SSL_CONF}" ]]; then
  sed "s/portal.justplay.vn/${DOMAIN}/g" PortalJustPlay/nginx/ssl.conf.example > "${SSL_CONF}"
fi

echo "==> 4) Enable HTTPS in .env"
if grep -q '^USE_HTTPS=' .env 2>/dev/null; then
  sed -i "s/^USE_HTTPS=.*/USE_HTTPS=1/" .env
else
  echo "USE_HTTPS=1" >> .env
fi

echo "==> 5) Restart with SSL"
compose_ssl up -d --build web nginx

echo ""
echo "SSL setup completed."
echo "  https://${DOMAIN}/"
echo ""
echo "Optional: redirect HTTP -> HTTPS in PortalJustPlay/nginx/default.conf"
echo "  Replace 'location / { proxy_pass ...' with 'return 301 https://\$host\$request_uri;'"
