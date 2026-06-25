#!/usr/bin/env bash
# Bổ sung / cập nhật tồn kho demo trên Odoo pilot.
set -euo pipefail
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
SCRIPT="${ODOO_DIR}/scripts/seed_stock_demo_data.py"
cd "$ODOO_DIR"
[[ -f "$SCRIPT" ]] || { echo "Thiếu $SCRIPT"; exit 1; }
docker compose exec -T odoo odoo shell -d "$DB_NAME" --no-http -c /etc/odoo/odoo.conf < "$SCRIPT"
echo "==> Xong. Mở Inventory → Products / On Hand trên https://erp.justplay.vn/"
