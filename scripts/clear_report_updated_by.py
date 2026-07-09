"""One-off: clear updated_by on production products for a report."""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth.models import User

from reports.models import DailyWorkReport, ProductionShiftProduct

report_id = int(sys.argv[1]) if len(sys.argv) > 1 else 3349
username = sys.argv[2] if len(sys.argv) > 2 else 'admin'

report = DailyWorkReport.objects.filter(pk=report_id).first()
if not report:
    print(f'Report {report_id} not found')
    sys.exit(1)

admin = User.objects.filter(username=username).first()
qs = ProductionShiftProduct.objects.filter(report_id=report_id)
before = list(qs.values_list('id', 'updated_by_id'))
print(f'Report {report_id} — products before: {before}')

if admin:
    cleared = qs.filter(updated_by_id=admin.id).update(updated_by_id=None)
else:
    cleared = qs.update(updated_by_id=None)

after = list(
    ProductionShiftProduct.objects.filter(report_id=report_id).values_list(
        'id', 'updated_by_id'
    )
)
print(f'Cleared {cleared} row(s) for user {username!r}')
print(f'After: {after}')
