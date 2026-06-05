#!/usr/bin/env bash
# Cron đồng bộ KiotViet mirror — mặc định mỗi 2 giờ (có thể đổi trên trang Quản Trị Hệ thống).
# Usage: sudo bash scripts/setup-kiotviet-cron.sh [INTERVAL_HOURS]

set -Eeuo pipefail

if ! command -v crontab >/dev/null 2>&1; then
  echo "==> Cài cron (chưa có trên server)..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cron
  systemctl enable cron
  systemctl start cron
fi

INTERVAL="${1:-2}"
PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="0 */${INTERVAL} * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync >> /var/log/portal-kiotviet-sync.log 2>&1"

TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'kiotviet_sync' > "${TMP}" || true
echo "${CRON_LINE}" >> "${TMP}"
crontab "${TMP}"
rm -f "${TMP}"

echo "Đã cấu hình cron KiotViet sync (mỗi ${INTERVAL} giờ):"
echo "  ${CRON_LINE}"
echo "  Log: /var/log/portal-kiotviet-sync.log"
echo "  Cấu hình mục sync: Quản Trị Hệ thống → Đồng bộ KiotViet"
