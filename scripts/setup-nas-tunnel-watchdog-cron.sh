#!/usr/bin/env bash
# Cron watchdog VPN site-to-site VPS <-> NAS — mỗi phút.
# Xem scripts/vps-nas-tunnel-watchdog.sh.
#
# Tắt bằng .env: NAS_TUNNEL_WATCHDOG=0 (script sẽ xóa cron nếu đang có).
# Usage: sudo bash scripts/setup-nas-tunnel-watchdog-cron.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
MARKER='vps-nas-tunnel-watchdog.sh'
CRON_LINE="* * * * * PROJECT_DIR=${PROJECT_DIR} /bin/bash ${PROJECT_DIR}/scripts/${MARKER} >> /var/log/portal-nas-watchdog.log 2>&1"

remove_cron() {
  local tmp
  tmp="$(mktemp)"
  crontab -l 2>/dev/null | grep -vF "${MARKER}" >"${tmp}" || true
  crontab "${tmp}"
  rm -f "${tmp}"
}

if grep -qE '^NAS_TUNNEL_WATCHDOG=(0|false|no|off)' "${PROJECT_DIR}/.env" 2>/dev/null; then
  if crontab -l 2>/dev/null | grep -qF "${MARKER}"; then
    remove_cron
    echo "NAS_TUNNEL_WATCHDOG đang tắt trong .env — đã xóa cron watchdog NAS."
  else
    echo "NAS_TUNNEL_WATCHDOG đang tắt trong .env — không cài cron."
  fi
  exit 0
fi

if crontab -l 2>/dev/null | grep -qF "${MARKER}"; then
  echo "Cron watchdog NAS đã tồn tại."
else
  (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -
  echo "Đã thêm cron watchdog VPN site-to-site NAS (mỗi phút)."
fi
