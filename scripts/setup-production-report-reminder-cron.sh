#!/usr/bin/env bash
# Cron tự động gửi báo cáo SX chưa nộp (trừ ca tối) — 11:30 hàng ngày (giờ VN trên VPS).
# Usage: sudo bash scripts/setup-production-report-reminder-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="30 11 * * * cd ${PROJECT_DIR} && /usr/bin/docker compose exec -T web python manage.py send_production_report_reminders --force >> /var/log/portal-prod-report-autosubmit.log 2>&1"

if crontab -l 2>/dev/null | grep -qF 'send_production_report_reminders'; then
  # Cập nhật dòng cron cũ (*/5) sang 11:30 nếu còn.
  tmp="$(mktemp)"
  crontab -l 2>/dev/null | grep -vF 'send_production_report_reminders' >"${tmp}" || true
  echo "${CRON_LINE}" >>"${tmp}"
  crontab "${tmp}"
  rm -f "${tmp}"
  echo "Đã cập nhật cron auto-submit BC SX lúc 11:30."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron auto-submit BC SX lúc 11:30."
fi

echo "Kiểm tra thử (dry-run, force hôm qua):"
cd "${PROJECT_DIR}"
docker compose exec -T web python manage.py send_production_report_reminders --dry-run --force
