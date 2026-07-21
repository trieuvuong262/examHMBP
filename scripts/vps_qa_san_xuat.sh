#!/usr/bin/env bash
# QA module Sản xuất trên VPS (trừ kho NPL & bán hàng).
# Chạy trên VPS: bash scripts/vps_qa_san_xuat.sh
set -euo pipefail
ROOT="${PORTAL_DIR:-/opt/portaljustplay}"
cd "$ROOT"
echo "==> VPS QA san_xuat @ $ROOT"
docker compose exec -T web python manage.py shell -c \
  "exec(open('scripts/vps_qa_san_xuat.py', encoding='utf-8').read())"
