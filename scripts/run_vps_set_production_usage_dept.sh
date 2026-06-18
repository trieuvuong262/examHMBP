#!/bin/bash
set -e
docker cp /tmp/vps_set_production_usage_dept.py portaljustplay-web-1:/app/scripts/vps_set_production_usage_dept.py
docker exec -w /app portaljustplay-web-1 python manage.py shell <<'PY'
exec(open('scripts/vps_set_production_usage_dept.py').read())
PY
