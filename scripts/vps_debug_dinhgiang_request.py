"""Debug yêu cầu Dinhgiang → giám đốc trên VPS."""
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

from hrm.module_permissions import MODULE_DE_XUAT, user_can_access_module
from hrm.permissions import ROLE_DIRECTOR, get_profile
from service_requests.models import RequestType, ServiceRequest, ServiceRequestStep
from service_requests.permissions import (
    can_handle_step,
    can_view_request,
    pending_steps_for_user,
)
from service_requests.workflow import find_director_user

User = get_user_model()

requester = User.objects.filter(username__iexact='Dinhgiang').first()
directors = list(
    User.objects.filter(
        is_active=True,
        profile__is_employed=True,
        profile__role=ROLE_DIRECTOR,
    ).select_related('profile'),
)

print('=== Users ===')
print('  requester:', requester.username if requester else None)
for d in directors:
    p = get_profile(d)
    print(f'  director: {d.username} | {p.full_name if p else "-"} | de_xuat={user_can_access_module(d, MODULE_DE_XUAT)}')
print('  find_director_user():', (find_director_user() or User()).username)

print('\n=== Requests from Dinhgiang ===')
if not requester:
    print('  NOT FOUND')
    raise SystemExit(1)

reqs = ServiceRequest.objects.filter(
    requester=requester,
    request_type__code=RequestType.CODE_ASSET_PURCHASE,
).prefetch_related('steps').order_by('-id')

if not reqs.exists():
    print('  no asset_purchase requests')
    raise SystemExit(0)

for req in reqs:
    print(f'\n--- Request #{req.pk}: {req.title} ---')
    print(f'  status={req.status}')
    print(f'  approval_tier={req.approval_tier!r}')
    print(f'  selected_total={req.selected_total_amount}')
    print(f'  is_from_catalog={req.is_from_catalog}')
    print(f'  needs_advance={req.needs_advance}')
    print('  steps:')
    for s in req.steps.order_by('step_order'):
        assignee = s.assignee.username if s.assignee_id else None
        dept = s.target_department.name if s.target_department_id else None
        print(
            f'    {s.step_order}. [{s.step_code}] {s.name} | '
            f'status={s.status} | rule={s.assignee_rule} | '
            f'assignee={assignee} | dept={dept}',
        )

    dir_steps = req.steps.filter(step_code=ServiceRequestStep.STEP_DIRECTOR)
    print(f'  director_steps: {dir_steps.count()}')
    for ds in dir_steps:
        print(f'    dir step status={ds.status} assignee={ds.assignee_id}')

    for d in directors:
        print(f'\n  Director {d.username}:')
        print(f'    can_view_request={can_view_request(d, req)}')
        pending = pending_steps_for_user(d).filter(request=req)
        print(f'    in_pending_list={pending.exists()} count={pending.count()}')
        for ps in pending:
            print(f'      pending step: {ps.name} ({ps.step_code}) status={ps.status}')
        for s in req.steps.filter(status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES):
            print(
                f'    can_handle [{s.step_code}] {s.name} = {can_handle_step(d, s)} '
                f'(assignee={s.assignee_id}, rule={s.assignee_rule})',
            )

    # HTTP test
    if directors:
        d = directors[0]
        client = Client(HTTP_HOST='portal.justplay.vn')
        client.force_login(d)
        for path in [
            '/yeu-cau/de-xuat/cho-xu-ly/',
            f'/yeu-cau/de-xuat/{req.pk}/',
        ]:
            r = client.get(path, follow=False)
            print(f'    HTTP {path} -> {r.status_code}', end='')
            if r.status_code == 302:
                print(f' -> {r.get("Location", "")}')
            else:
                body = r.content.decode('utf-8', errors='replace')
                has_title = req.title[:20] in body
                print(f' | title_in_page={has_title}')

        r = client.get('/yeu-cau/de-xuat/cho-xu-ly/')
        body = r.content.decode('utf-8', errors='replace')
        print(f'    pending page has req#{req.pk} title: {req.title[:30] in body}')

print('\n=== All open director steps in system ===')
open_dir = ServiceRequestStep.objects.filter(
    step_code=ServiceRequestStep.STEP_DIRECTOR,
    status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES,
).select_related('request', 'assignee', 'request__requester')
print('  count:', open_dir.count())
for s in open_dir:
    print(
        f'  req#{s.request_id} from {s.request.requester.username} | '
        f'status={s.status} assignee={s.assignee.username if s.assignee_id else None}',
    )
