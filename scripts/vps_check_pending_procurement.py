"""Kiểm tra ai thấy bước Thu mua sau duyệt TBP trên VPS — chạy: python manage.py shell < scripts/vps_check_pending_procurement.py"""
from django.contrib.auth import get_user_model

from service_requests.models import ServiceRequest
from service_requests.permissions import can_handle_step, pending_steps_for_user
from service_requests.workflow import get_accounting_department, get_procurement_department

User = get_user_model()

procurement_dept = get_procurement_department()
accounting_dept = get_accounting_department()
print('=== Departments ===')
print('  procurement:', procurement_dept.name if procurement_dept else None)
print('  accounting:', accounting_dept.name if accounting_dept else None)

req = ServiceRequest.objects.filter(pk=8).first()
if not req:
    print('Request #8 not found')
else:
    print(f'\n=== Request #{req.pk}: {req.title} ===')
    cs = req.current_step
    print(f'  current_step={cs.step_code if cs else None} assignee={cs.assignee.username if cs and cs.assignee_id else None}')
    for s in req.steps.order_by('step_order'):
        assignee = s.assignee.username if s.assignee_id else None
        print(f'  {s.step_order}. [{s.step_code}] status={s.status} assignee={assignee}')

    for uname in ['vananh', 'thiray', 'dththuy', 'Ductn', 'Dinhgiang']:
        user = User.objects.filter(username__iexact=uname).first()
        if not user:
            continue
        pending = list(pending_steps_for_user(user).filter(request=req))
        handle = can_handle_step(user, cs) if cs else False
        print(f'  {uname}: pending={len(pending)} {[p.step_code for p in pending]} can_handle={handle}')
