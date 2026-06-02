#!/usr/bin/env bash
# Cron backup Portal (DB + source + media) lên NAS — 02:00 hàng ngày.
# Usage: sudo bash scripts/setup-backup-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="0 2 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py backup_to_nas >> /var/log/portal-backup-nas.log 2>&1"

if crontab -l 2>/dev/null | grep -qF 'backup_to_nas'; then
  echo "Cron backup_to_nas đã tồn tại."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron: ${CRON_LINE}"
fi

echo "Kiểm tra thử (có thể mất vài phút):"
cd "${PROJECT_DIR}"
docker compose exec -T web python manage.py backup_to_nas
