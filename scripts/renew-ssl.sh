#!/bin/bash
set -euo pipefail

# Gia hạn Let's Encrypt (portal + erp) rồi restart nginx khi cert đổi.
# Chạy trên VPS. Cron: 15 4 * * * /usr/local/sbin/portal-renew-ssl.sh >> /var/log/portal-ssl-renew.log 2>&1

LOG_TS() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }

CERTBOT_VOL="$(docker volume ls -q | grep certbot_webroot | head -1 || true)"
if [[ -z "${CERTBOT_VOL}" ]]; then
  echo "$(LOG_TS) ERROR: certbot_webroot volume not found"
  exit 1
fi

fingerprint() {
  local f="$1"
  if [[ -f "$f" ]]; then
    openssl x509 -in "$f" -noout -fingerprint -sha256 2>/dev/null || echo missing
  else
    echo missing
  fi
}

PORTAL_FP_BEFORE="$(fingerprint /etc/letsencrypt/live/portal.justplay.vn/fullchain.pem)"
ERP_FP_BEFORE="$(fingerprint /etc/letsencrypt/live/erp.justplay.vn/fullchain.pem)"

docker run --rm \
  -v "${CERTBOT_VOL}:/var/www/certbot" \
  -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot renew --quiet --non-interactive --agree-tos

PORTAL_FP_AFTER="$(fingerprint /etc/letsencrypt/live/portal.justplay.vn/fullchain.pem)"
ERP_FP_AFTER="$(fingerprint /etc/letsencrypt/live/erp.justplay.vn/fullchain.pem)"

if [[ "${PORTAL_FP_BEFORE}" != "${PORTAL_FP_AFTER}" || "${ERP_FP_BEFORE}" != "${ERP_FP_AFTER}" ]]; then
  echo "$(LOG_TS) cert changed — restart nginx"
  docker restart portaljustplay-nginx-1 >/dev/null
else
  echo "$(LOG_TS) certs unchanged — skip nginx restart"
fi
