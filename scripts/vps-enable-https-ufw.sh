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

echo "==> [3/3] Bật UFW — SSH whitelist + HTTP/HTTPS public"
bash "$PROJECT_DIR/scripts/vps-ufw-ssh-whitelist.sh"

echo "==> Hoàn tất"
