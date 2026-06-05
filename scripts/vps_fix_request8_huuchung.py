"""Gán bước Tổ trưởng duyệt yêu cầu #8 cho huuchung."""
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

from service_requests.models import ServiceRequest, ServiceRequestStep
from service_requests.permissions import can_handle_step, pending_steps_for_user

User = get_user_model()

requester = User.objects.get(username__iexact='Dinhgiang')
huuchung = User.objects.get(username__iexact='huuchung')
req = ServiceRequest.objects.get(pk=8, requester=requester)

step = req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER)
print('Before:', step.name, step.status, 'assignee=', step.assignee_id)

step.assignee = huuchung
step.status = ServiceRequestStep.STATUS_PENDING
step.save(update_fields=['assignee', 'status'])

# Cấp trên trực tiếp trong HRM — tránh kẹt lần sau
profile = huuchung.profile
if not profile.subordinates.filter(pk=requester.pk).exists():
    profile.subordinates.add(requester)
    print('Added Dinhgiang to huuchung subordinates')

print('After:', step.assignee.username, step.status)
print('huuchung can_handle:', can_handle_step(huuchung, step))
print('huuchung pending:', pending_steps_for_user(huuchung).filter(request=req).count())

client = Client(HTTP_HOST='portal.justplay.vn')
client.force_login(huuchung)
r = client.get('/yeu-cau/de-xuat/cho-xu-ly/')
body = r.content.decode('utf-8', errors='replace')
print('HTTP cho-xu-ly:', r.status_code, 'has_title:', req.title[:25] in body)
