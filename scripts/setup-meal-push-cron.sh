#!/usr/bin/env bash
# Cron gửi web push nhắc đặt cơm — 16:00 và 17:00 hàng ngày (giờ VN trên VPS).
# Usage: sudo bash scripts/setup-meal-push-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_16="0 16 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py send_meal_push_reminders >> /var/log/portal-meal-push.log 2>&1"
CRON_17="0 17 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py send_meal_push_reminders >> /var/log/portal-meal-push.log 2>&1"

append_cron() {
  local line="$1"
  if crontab -l 2>/dev/null | grep -qF 'send_meal_push_reminders'; then
    echo "Cron send_meal_push_reminders đã tồn tại."
  else
    (crontab -l 2>/dev/null; echo "${line}"; echo "${CRON_17}") | crontab -
    echo "Đã thêm cron nhắc đặt cơm 16:00 và 17:00."
  fi
}

append_cron "${CRON_16}"

echo "Kiểm tra thử (dry-run):"
cd "${PROJECT_DIR}"
docker compose exec -T web python manage.py send_meal_push_reminders --dry-run
