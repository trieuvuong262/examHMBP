#!/usr/bin/env bash
# Cron đồng bộ KiotViet mirror — incremental (chỉ mới/thay đổi).
# Usage: sudo bash scripts/setup-kiotviet-cron.sh [INTERVAL_MINUTES]
# INTERVAL_MINUTES: 5 | 30 | 360 | 720 | 1440

set -Eeuo pipefail

if ! command -v crontab >/dev/null 2>&1; then
  echo "==> Cài cron (chưa có trên server)..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cron
  systemctl enable cron
  systemctl start cron
fi

MINUTES="${1:-30}"
PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"

case "${MINUTES}" in
  5)   CRON_LINE="*/5 * * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync >> /var/log/portal-kiotviet-sync.log 2>&1" ;;
  30)  CRON_LINE="*/30 * * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync >> /var/log/portal-kiotviet-sync.log 2>&1" ;;
  360) CRON_LINE="0 */6 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync >> /var/log/portal-kiotviet-sync.log 2>&1" ;;
  720) CRON_LINE="0 */12 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync >> /var/log/portal-kiotviet-sync.log 2>&1" ;;
  1440) CRON_LINE="0 2 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync >> /var/log/portal-kiotviet-sync.log 2>&1" ;;
  *)
    echo "INTERVAL_MINUTES không hợp lệ: ${MINUTES}. Dùng: 5, 30, 360, 720, 1440"
    exit 1
    ;;
esac

TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'kiotviet_sync' > "${TMP}" || true
echo "${CRON_LINE}" >> "${TMP}"
crontab "${TMP}"
rm -f "${TMP}"

echo "Đã cấu hình cron KiotViet sync (mỗi ${MINUTES} phút, incremental):"
echo "  ${CRON_LINE}"
echo "  Log: /var/log/portal-kiotviet-sync.log"
echo "  Cấu hình mục sync: Quản Trị Hệ thống → Đồng bộ KiotViet"
