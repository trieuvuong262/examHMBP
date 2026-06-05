"""E2E: tạo đề xuất thử trên VPS (admin), kiểm tra workflow."""
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

from service_requests.models import RequestType, ServiceRequest, ServiceRequestStep
from service_requests.permissions import can_manage_recurring_catalog
from service_requests.workflow import get_active_request_type

User = get_user_model()
admin = User.objects.filter(username='admin', is_active=True).first()
if not admin:
    admin = User.objects.filter(is_superuser=True, is_active=True).first()

print('=== Workflow config ===')
rt = get_active_request_type()
print('  active_request_type:', rt.code if rt else None, rt.name if rt else '')
if rt:
    from service_requests.models import RequestTypeStepTemplate
    templates = RequestTypeStepTemplate.objects.filter(request_type=rt).order_by('step_order')
    print('  workflow_steps:', templates.count())
    for t in templates:
        print(f'    {t.step_order}. {t.name} ({t.step_kind})')

print('  can_manage_catalog(admin):', can_manage_recurring_catalog(admin))

client = Client(HTTP_HOST='portal.justplay.vn')
client.force_login(admin)

# GET form
r = client.get('/yeu-cau/de-xuat/tao/')
print('\n=== Create form GET ===')
print('  status:', r.status_code)
print('  has form:', b'name="title"' in r.content)

# POST create (test data)
before = ServiceRequest.objects.filter(request_type__code=RequestType.CODE_ASSET_PURCHASE).count()
payload = {
    'title': '[VPS-TEST] Đề xuất kiểm tra tự động',
    'description': 'Tự động kiểm tra sau deploy — có thể hủy/xóa.',
    'needs_advance': '',
    'lines-TOTAL_FORMS': '1',
    'lines-INITIAL_FORMS': '0',
    'lines-MIN_NUM_FORMS': '0',
    'lines-MAX_NUM_FORMS': '1000',
    'lines-0-description': 'Vật tư test kiểm tra VPS',
    'lines-0-quantity': '1',
    'lines-0-unit': 'cái',
    'lines-0-DELETE': '',
}
r2 = client.post('/yeu-cau/de-xuat/tao/', payload, follow=False)
print('\n=== Create POST ===')
print('  status:', r2.status_code)
print('  location:', r2.get('Location', ''))

after = ServiceRequest.objects.filter(request_type__code=RequestType.CODE_ASSET_PURCHASE).count()
print('  requests before/after:', before, after)

req = ServiceRequest.objects.filter(title__startswith='[VPS-TEST]').order_by('-id').first()
if req:
    print('\n=== Created request ===')
    print('  id:', req.pk)
    print('  status:', req.status)
    print('  requester:', req.requester.username)
    steps = ServiceRequestStep.objects.filter(request=req).order_by('step_order')
    print('  steps:', steps.count())
    for s in steps:
        print(f'    {s.step_order}. {s.name} status={s.status} assignee={s.assignee_id}')

    detail = client.get(f'/yeu-cau/de-xuat/{req.pk}/')
    print('  detail page:', detail.status_code)

    # cleanup — cancel not delete to preserve audit
    from service_requests.workflow import cancel_request
    cancel_request(req, actor=admin, reason='VPS auto-test cleanup')
    req.refresh_from_db()
    print('  cancelled, status:', req.status)
else:
    print('  CREATE FAILED — no request found')
    if r2.status_code == 200:
        body = r2.content.decode('utf-8', errors='replace')
        if 'alert-danger' in body or 'errorlist' in body:
            import re
            errs = re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', body)
            print('  form errors snippet:', errs[:5])

print('\nDone.')
