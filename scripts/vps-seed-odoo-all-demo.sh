#!/usr/bin/env bash
# Chạy toàn bộ demo Odoo pilot: MRP → tồn kho → module còn lại.
set -euo pipefail
ODOO_DIR="${ODOO_DIR:-/opt/odoo}"
DB_NAME="${ODOO_PILOT_DB:-justplay_pilot}"
cd "$ODOO_DIR"
run() {
  local f="$1"
  [[ -f "$f" ]] || { echo "Thiếu $f"; exit 1; }
  echo "==> $f"
  docker compose exec -T odoo odoo shell -d "$DB_NAME" --no-http -c /etc/odoo/odoo.conf < "$f"
}
run "${ODOO_DIR}/scripts/seed_mrp_demo_data.py"
run "${ODOO_DIR}/scripts/seed_stock_demo_data.py"
run "${ODOO_DIR}/scripts/seed_odoo_pilot_demo.py"
run "${ODOO_DIR}/scripts/seed_odoo_pilot_demo_expand.py"
echo "==> Xong toàn bộ demo — https://erp.justplay.vn/"
