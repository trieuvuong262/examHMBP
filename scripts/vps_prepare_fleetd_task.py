# -*- coding: utf-8 -*-
"""Chuẩn bị demo trên VPS: huỷ việc fleetd-base cũ chưa xong, in quyền giao việc.

Chạy trên VPS:
  docker compose exec -T web python manage.py shell < scripts/vps_prepare_fleetd_task.py
"""
from django.contrib.auth.models import User

from hrm.permissions import (
    can_assign_tasks,
    can_receive_assigned_tasks,
    get_task_assignable_users,
)
from tasks.models import WorkTask, WorkTaskLog
from tasks.utils import log_task_action

MGR = 'Vuonglnt'
EMP = 'long.tb'

mgr = User.objects.get(username=MGR)
emp = User.objects.get(username=EMP)

print(f'mgr pk={mgr.pk} role={getattr(mgr.profile, "role", None)}')
print(f'emp pk={emp.pk} role={getattr(emp.profile, "role", None)}')
print(f'can_assign_tasks(mgr)={can_assign_tasks(mgr)}')
print(f'can_receive_assigned_tasks(emp)={can_receive_assigned_tasks(emp)}')

qs = get_task_assignable_users(mgr)
print(f'assignable_count={qs.count()}')
print(f'emp_in_assignable={qs.filter(pk=emp.pk).exists()}')
if not qs.filter(pk=emp.pk).exists():
    names = list(qs.values_list('username', flat=True)[:20])
    print(f'assignable_sample={names}')

open_qs = WorkTask.objects.filter(
    project__isnull=True,
    assigner=mgr,
    assignee=emp,
    title__icontains='fleetd-base',
).exclude(status__in=[
    WorkTask.STATUS_COMPLETED,
    WorkTask.STATUS_CANCELLED,
    WorkTask.STATUS_REASSIGNED,
])
n = 0
for t in open_qs:
    t.status = WorkTask.STATUS_CANCELLED
    t.save(update_fields=['status', 'updated_at'])
    log_task_action(t, mgr, WorkTaskLog.ACTION_CANCEL, 'Huỷ bản demo cũ trước khi tạo lại')
    n += 1
print(f'cancelled_old={n}')
print('READY')
