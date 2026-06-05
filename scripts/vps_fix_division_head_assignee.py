import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from service_requests.models import ServiceRequestStep
from service_requests.workflow import find_director_user, find_division_head_manager

director = find_director_user()
print('director:', director.username if director else None)

fixed = 0
for step in ServiceRequestStep.objects.filter(
    step_code=ServiceRequestStep.STEP_DIVISION_HEAD,
    assignee__isnull=True,
).select_related('request__requester'):
    assignee = find_division_head_manager(step.request.requester)
    if assignee:
        step.assignee = assignee
        step.save(update_fields=['assignee'])
        fixed += 1
        print(f'  req#{step.request_id} -> {assignee.username}')

print('fixed:', fixed)
