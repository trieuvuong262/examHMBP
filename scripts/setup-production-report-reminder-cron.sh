#!/usr/bin/env bash
# Cron tự động gửi báo cáo SX ca sáng chưa nộp (trừ ca tối).
# Chạy mỗi 5 phút — giờ nộp lấy từ Thiết lập chung báo cáo (cửa sổ grace 5 phút).
# Usage: sudo bash scripts/setup-production-report-reminder-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="*/5 * * * * cd ${PROJECT_DIR} && /usr/bin/docker compose exec -T web python manage.py send_production_report_reminders >> /var/log/portal-prod-report-autosubmit.log 2>&1"

if crontab -l 2>/dev/null | grep -qF 'send_production_report_reminders'; then
  tmp="$(mktemp)"
  crontab -l 2>/dev/null | grep -vF 'send_production_report_reminders' >"${tmp}" || true
  echo "${CRON_LINE}" >>"${tmp}"
  crontab "${tmp}"
  rm -f "${tmp}"
  echo "Đã cập nhật cron auto-submit BC SX mỗi 5 phút (giờ theo Thiết lập chung)."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron auto-submit BC SX mỗi 5 phút (giờ theo Thiết lập chung)."
fi

echo "Kiểm tra thử (dry-run, force hôm nay):"
cd "${PROJECT_DIR}"
docker compose exec -T web python manage.py send_production_report_reminders --dry-run --force
