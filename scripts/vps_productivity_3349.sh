#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PY'
from reports.models import DailyWorkReport
from reports.production_hourly import build_productivity_report

r = DailyWorkReport.objects.get(pk=3349)
p = build_productivity_report(r)
for row in p['product_summaries']:
    print(row['product_code'], '|', repr(row.get('updated_by_name')))
print('proxy_entered_by_name:', repr(p.get('proxy_entered_by_name')))
PY
