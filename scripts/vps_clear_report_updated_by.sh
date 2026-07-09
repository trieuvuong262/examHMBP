#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PY'
from django.contrib.auth.models import User
from reports.models import ProductionShiftProduct

report_id = 3349
admin = User.objects.filter(username='admin').first()
qs = ProductionShiftProduct.objects.filter(report_id=report_id)
before = list(qs.values_list('id', 'updated_by_id'))
print('before:', before)
if admin:
    n = qs.filter(updated_by_id=admin.id).update(updated_by_id=None)
else:
    n = qs.update(updated_by_id=None)
after = list(ProductionShiftProduct.objects.filter(report_id=report_id).values_list('id', 'updated_by_id'))
print('cleared:', n)
print('after:', after)
PY
