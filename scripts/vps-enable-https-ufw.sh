#!/usr/bin/env bash
# Bật redirect HTTP→HTTPS (nginx) + UFW chỉ 22/80/443
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
cd "$PROJECT_DIR"

echo "==> [1/3] Kiểm tra nginx config"
docker compose exec -T nginx nginx -t

echo "==> [2/3] Reload nginx"
docker compose exec -T nginx nginx -s reload
echo "    HTTP redirect test:"
curl -s -o /dev/null -w '    http://portal.justplay.vn -> %{http_code} %{redirect_url}\n' http://portal.justplay.vn/accounts/login/ || true

echo "==> [3/3] Bật UFW (22, 80, 443)"
if ! command -v ufw >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ufw
fi
# Docker cần forward — không chặn bridge
if [[ -f /etc/ufw/ufw.conf ]] && grep -q '^DEFAULT_FORWARD_POLICY=' /etc/ufw/ufw.conf; then
  sed -i 's/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/ufw/ufw.conf
fi

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'

if ufw status | grep -qi 'Status: active'; then
  echo "    UFW đã active — rules updated"
else
  ufw --force enable
  echo "    UFW enabled"
fi

ufw status verbose

echo "==> Hoàn tất"
