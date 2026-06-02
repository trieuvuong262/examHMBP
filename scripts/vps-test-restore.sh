#!/usr/bin/env bash
# Kiểm tra khôi phục từ backup NAS (DB tạm — không ghi đè production).
# Usage: sudo bash scripts/vps-test-restore.sh [remote_folder]
# Ví dụ: sudo bash scripts/vps-test-restore.sh synology:backup/2026-06-02/20260602-165908-man

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
cd "${PROJECT_DIR}"

REMOTE="${1:-}"
if [[ -z "${REMOTE}" ]]; then
  DAY=$(date +%Y-%m-%d)
  RUN=$(docker compose exec -T web rclone lsf "synology:backup/${DAY}/" --dirs-only 2>/dev/null | tr -d '\r' | sort | tail -1)
  REMOTE="synology:backup/${DAY}/${RUN}"
  REMOTE="${REMOTE%/}"
fi

echo "==> Backup remote: ${REMOTE}"

docker compose exec -T web python manage.py verify_nas_backup_restore --remote="${REMOTE}"
