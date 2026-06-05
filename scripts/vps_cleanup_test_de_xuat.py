import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from service_requests.models import ServiceRequest
from service_requests.workflow import cancel_request

User = get_user_model()
admin = User.objects.filter(username='admin').first()
for req in ServiceRequest.objects.filter(title__startswith='[VPS-TEST]'):
    if req.status == ServiceRequest.STATUS_IN_PROGRESS and admin:
        cancel_request(req, actor=admin)
        print('cancelled', req.pk)
    else:
        print('skip', req.pk, req.status)
