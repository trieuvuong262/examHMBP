#!/usr/bin/env bash
# Kiểm tra + chạy thử backup lên NAS trên VPS.
# Usage: sudo bash scripts/vps-test-backup.sh

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/portaljustplay}"
cd "${PROJECT_DIR}"

compose() {
  COMPOSE_BAKE=false docker compose "$@"
}

echo "==> 1) rclone synology:backup"
if compose exec -T web rclone lsd synology:backup; then
  echo "    OK: thư mục backup trên NAS truy cập được"
else
  echo "    LOI: Không list được synology:backup"
  echo "    Tạo shared folder 'backup' trên Synology (cùng user SMB như DATACHUNG)"
  exit 1
fi

echo "==> 2) migrate (PortalBackupJob)"
compose exec -T web python manage.py migrate audit --noinput

echo "==> 3) Chạy backup thử (có thể 2–10 phút)"
compose exec -T web python manage.py backup_to_nas

echo "==> 4) Liệt kê bản backup mới nhất"
compose exec -T web rclone lsd synology:backup
echo "    Chi tiết:"
compose exec -T web rclone ls synology:backup --max-depth 3 | tail -20

echo "==> Xong. Kiểm tra File Station → share/folder backup trên NAS."
