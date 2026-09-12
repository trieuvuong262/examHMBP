#!/usr/bin/env bash
# Cron đồng bộ KiotViet mirror — incremental (chỉ mới/thay đổi).
# Usage: sudo bash scripts/setup-kiotviet-cron.sh [INTERVAL]
# INTERVAL: 481 (6h·12h·19h) | 5 | 30 | 360 | 720 | 1440

set -Eeuo pipefail

if ! command -v crontab >/dev/null 2>&1; then
  echo "==> Cài cron (chưa có trên server)..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cron
  systemctl enable cron
  systemctl start cron
fi

MINUTES="${1:-481}"
PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
SYNC_CMD="cd ${PROJECT_DIR} && docker compose exec -T web python manage.py kiotviet_sync --scheduled >> /var/log/portal-kiotviet-sync.log 2>&1"

case "${MINUTES}" in
  481) CRON_LINE="0 6,12,19 * * * ${SYNC_CMD}" ;;
  5)   CRON_LINE="*/5 * * * * ${SYNC_CMD}" ;;
  30)  CRON_LINE="*/30 * * * * ${SYNC_CMD}" ;;
  360) CRON_LINE="0 */6 * * * ${SYNC_CMD}" ;;
  720) CRON_LINE="0 */12 * * * ${SYNC_CMD}" ;;
  1440) CRON_LINE="0 2 * * * ${SYNC_CMD}" ;;
  *)
    echo "INTERVAL không hợp lệ: ${MINUTES}. Dùng: 481, 5, 30, 360, 720, 1440"
    exit 1
    ;;
esac

TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'kiotviet_sync' > "${TMP}" || true
echo "${CRON_LINE}" >> "${TMP}"
crontab "${TMP}"
rm -f "${TMP}"

echo "Đã cấu hình cron KiotViet sync (interval=${MINUTES}, incremental, tất cả entity đã bật):"
echo "  ${CRON_LINE}"
echo "  Log: /var/log/portal-kiotviet-sync.log"
echo "  Cấu hình mục sync: Quản Trị Hệ thống → Đồng bộ KiotViet"
