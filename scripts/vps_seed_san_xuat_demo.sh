#!/usr/bin/env bash
# Seed demo Sản xuất trên VPS (hiển thị UI, không kho NPL / bán hàng).
# Chạy: bash scripts/vps_seed_san_xuat_demo.sh
#       bash scripts/vps_seed_san_xuat_demo.sh --clear
set -euo pipefail
ROOT="${PORTAL_DIR:-/opt/portaljustplay}"
cd "$ROOT"
EXTRA="${*:-}"
echo "==> Seed demo san_xuat @ $ROOT"
docker compose exec -T web python manage.py seed_san_xuat_vps_demo $EXTRA
