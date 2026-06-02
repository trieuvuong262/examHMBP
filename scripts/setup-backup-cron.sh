#!/usr/bin/env bash
# Cron backup Portal (DB + source + media) lên NAS — 00:00 mỗi ngày (giờ server VPS).
# Usage: sudo bash scripts/setup-backup-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="0 0 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py backup_to_nas >> /var/log/portal-backup-nas.log 2>&1"

TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'backup_to_nas' > "${TMP}" || true
echo "${CRON_LINE}" >> "${TMP}"
crontab "${TMP}"
rm -f "${TMP}"

echo "Đã cấu hình cron backup (00:00 hàng ngày):"
echo "  ${CRON_LINE}"
echo "  Log: /var/log/portal-backup-nas.log"
echo "  NAS: synology:backup/YYYY-MM-DD/"
