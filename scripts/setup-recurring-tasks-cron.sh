#!/usr/bin/env bash
# Cài cron tạo công việc lặp hàng ngày trên VPS.
# Usage: sudo bash scripts/setup-recurring-tasks-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="0 6 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py generate_recurring_tasks >> /var/log/portal-recurring-tasks.log 2>&1"

if crontab -l 2>/dev/null | grep -qF 'generate_recurring_tasks'; then
  echo "Cron generate_recurring_tasks đã tồn tại."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron: ${CRON_LINE}"
fi

echo "Kiểm tra thử:"
cd "${PROJECT_DIR}"
docker compose exec -T web python manage.py generate_recurring_tasks
