#!/usr/bin/env bash
# Cron xóa nhật ký thao tác cũ hơn 7 ngày — 03:15 mỗi ngày (giờ server VPS).
# Usage: sudo bash scripts/setup-activity-log-cleanup-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="15 3 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py cleanup_activity_logs >> /var/log/portal-activity-log-cleanup.log 2>&1"

if crontab -l 2>/dev/null | grep -qF 'cleanup_activity_logs'; then
  echo "Cron cleanup_activity_logs đã tồn tại."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron: ${CRON_LINE}"
fi
