#!/usr/bin/env bash
# Tạo dữ liệu demo Sản xuất (MRP) trên Odoo pilot.
set -euo pipefail
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
SCRIPT="${ODOO_DIR}/scripts/seed_mrp_demo_data.py"
cd "$ODOO_DIR"
if [[ ! -f "$SCRIPT" ]]; then
  echo "Thiếu $SCRIPT — copy odoo/scripts/ lên VPS trước."
  exit 1
fi
docker compose exec -T odoo odoo shell -d "$DB_NAME" --no-http -c /etc/odoo/odoo.conf < "$SCRIPT"
echo "==> Xong. Mở Manufacturing trên https://erp.justplay.vn/"
