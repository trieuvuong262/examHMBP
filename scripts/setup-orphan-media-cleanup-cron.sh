#!/usr/bin/env bash
# Cron dọn file media không còn được DB/HTML tham chiếu — 03:40 mỗi ngày.
#
# Trước đây bước này chạy trong deploy.sh, nhưng nó quét toàn bộ row của mọi model
# có FileField/ImageField/RichTextField rồi rglob toàn bộ MEDIA_ROOT → thời gian
# tăng theo kích thước dữ liệu và không liên quan gì tới việc lên bản mới.
#
# Tắt bằng .env: CLEANUP_ORPHAN_MEDIA=0 (script sẽ xóa cron nếu đang có).
# Usage: sudo bash scripts/setup-orphan-media-cleanup-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
CRON_LINE="40 3 * * * cd ${PROJECT_DIR} && docker compose exec -T web python manage.py cleanup_orphan_media >> /var/log/portal-orphan-media-cleanup.log 2>&1"

if grep -qE '^CLEANUP_ORPHAN_MEDIA=(0|false|no|off)' "${PROJECT_DIR}/.env" 2>/dev/null; then
  if crontab -l 2>/dev/null | grep -qF 'cleanup_orphan_media'; then
    tmp="$(mktemp)"
    crontab -l 2>/dev/null | grep -vF 'cleanup_orphan_media' >"${tmp}" || true
    crontab "${tmp}"
    rm -f "${tmp}"
    echo "CLEANUP_ORPHAN_MEDIA đang tắt trong .env — đã xóa cron cleanup_orphan_media."
  else
    echo "CLEANUP_ORPHAN_MEDIA đang tắt trong .env — không cài cron."
  fi
  exit 0
fi

if crontab -l 2>/dev/null | grep -qF 'cleanup_orphan_media'; then
  echo "Cron cleanup_orphan_media đã tồn tại."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron dọn media mồ côi (03:40 hàng ngày)."
fi
