"""Phân tích vì sao giám đốc không thấy yêu cầu mua hàng trên VPS."""
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from django.contrib.auth import get_user_model
from hrm.module_permissions import MODULE_DE_XUAT, user_can_access_module
from hrm.permissions import ROLE_DIRECTOR, get_profile
from service_requests.models import RequestType, ServiceRequest, ServiceRequestStep
from service_requests.permissions import can_view_request, pending_steps_for_user
from service_requests.workflow import AMOUNT_ACCOUNTING_MIN, AMOUNT_DIRECTOR_MIN, find_director_user

User = get_user_model()

print('=== Ngưỡng duyệt ===')
print(f'  Kế toán: >= {AMOUNT_ACCOUNTING_MIN:,.0f} VNĐ')
print(f'  Giám đốc: >= {AMOUNT_DIRECTOR_MIN:,.0f} VNĐ')

print('\n=== Giám đốc trong hệ thống ===')
directors = User.objects.filter(
    is_active=True,
    profile__is_employed=True,
    profile__role=ROLE_DIRECTOR,
).select_related('profile')
print('  count:', directors.count())
for d in directors:
    print(
        f'  - {d.username}: {d.profile.full_name or "-"} | '
        f'module_de_xuat={user_can_access_module(d, MODULE_DE_XUAT)} | '
        f'pending={pending_steps_for_user(d).filter(request__request_type__code=RequestType.CODE_ASSET_PURCHASE).count()}',
    )

assigned = find_director_user()
print('\n  find_director_user():', assigned.username if assigned else None)

print('\n=== Yêu cầu mua hàng đang xử lý ===')
active = ServiceRequest.objects.filter(
    request_type__code=RequestType.CODE_ASSET_PURCHASE,
    status=ServiceRequest.STATUS_IN_PROGRESS,
).prefetch_related('steps')
print('  count:', active.count())
for req in active[:15]:
    steps = list(req.steps.order_by('step_order'))
    active_step = next(
        (s for s in steps if s.status in ServiceRequestStep.OPEN_HANDLER_STATUSES),
        None,
    )
    has_dir = any(s.step_code == ServiceRequestStep.STEP_DIRECTOR for s in steps)
    print(f'  #{req.pk} {req.title[:40]} | tier={req.approval_tier or "-"} | total={req.selected_total_amount or "-"}')
    print(f'      requester={req.requester.username} | active={active_step.name if active_step else "-"} ({active_step.status if active_step else "-"})')
    print(f'      has_director_step={has_dir} | from_catalog={req.is_from_catalog}')
    if directors.exists():
        d = directors.first()
        print(f'      director_can_view={can_view_request(d, req)} | director_pending={pending_steps_for_user(d).filter(request=req).exists()}')

print('\n=== Tóm tắt theo giai đoạn ===')
all_reqs = ServiceRequest.objects.filter(request_type__code=RequestType.CODE_ASSET_PURCHASE)
print('  total:', all_reqs.count())
print('  in_progress:', all_reqs.filter(status=ServiceRequest.STATUS_IN_PROGRESS).count())
print('  with director step:', all_reqs.filter(steps__step_code=ServiceRequestStep.STEP_DIRECTOR).distinct().count())
print('  director step pending:', ServiceRequestStep.objects.filter(
    step_code=ServiceRequestStep.STEP_DIRECTOR,
    status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES,
).count())
