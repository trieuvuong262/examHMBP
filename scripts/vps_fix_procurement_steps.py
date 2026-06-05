import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from service_requests.models import ServiceRequestStep
from service_requests.workflow import get_procurement_department

dept = get_procurement_department()
print('procurement dept:', dept.name if dept else None)
if not dept:
    raise SystemExit(1)

updated = ServiceRequestStep.objects.filter(
    step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE,
    target_department__isnull=True,
).update(target_department=dept)
print('updated quote steps:', updated)
