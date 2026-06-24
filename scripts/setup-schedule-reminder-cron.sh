#!/usr/bin/env bash
# Cron gửi web push nhắc lịch — mỗi phút (giờ VN trên VPS).
# Usage: sudo bash scripts/setup-schedule-reminder-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="* * * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py send_schedule_reminder_pushes >> /var/log/portal-schedule-reminder-push.log 2>&1"

if crontab -l 2>/dev/null | grep -qF 'send_schedule_reminder_pushes'; then
  echo "Cron send_schedule_reminder_pushes đã tồn tại."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron nhắc lịch (mỗi phút)."
fi

echo "Kiểm tra thử (dry-run):"
cd "${PROJECT_DIR}"
docker compose exec -T web python manage.py send_schedule_reminder_pushes --dry-run
