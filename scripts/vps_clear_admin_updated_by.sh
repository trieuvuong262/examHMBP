#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PY'
from reports.models import ProductionShiftProduct

n = ProductionShiftProduct.objects.filter(updated_by__username='admin').update(updated_by_id=None)
print('cleared_admin_globally:', n)
PY
