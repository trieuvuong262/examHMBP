#!/usr/bin/env bash
# Chạy trên VPS: bash scripts/vps_qa_ie_import_export.sh
set -euo pipefail
ROOT="${PORTAL_DIR:-/opt/portaljustplay}"
cd "$ROOT"
echo "==> VPS QA IE import/export @ $ROOT"
# Script vừa scp lên host — copy vào container (image không có file mới)
docker compose cp scripts/vps_qa_ie_import_export.py web:/app/scripts/vps_qa_ie_import_export.py
docker compose exec -T web python manage.py shell <<'PY'
exec(open("/app/scripts/vps_qa_ie_import_export.py", encoding="utf-8").read())
PY
