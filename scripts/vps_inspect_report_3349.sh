#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PY'
from reports.models import DailyWorkReport, ProductionShiftProduct

r = DailyWorkReport.objects.select_related('proxy_entered_by', 'proxy_entered_by__profile').get(pk=3349)
pe = r.proxy_entered_by
print('proxy_entered_by_id:', r.proxy_entered_by_id)
if pe:
    print('proxy_username:', pe.username)
    p = getattr(pe, 'profile', None)
    print('proxy_full_name:', getattr(p, 'full_name', None) if p else None)

for p in ProductionShiftProduct.objects.filter(report_id=3349):
    ub = p.updated_by
    print('product', p.id, 'updated_by', p.updated_by_id, ub.username if ub else None)
PY
