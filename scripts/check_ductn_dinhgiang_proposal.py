"""Kiểm tra VPS: phiếu đề xuất dinhgiang — ductn có thấy không."""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User

from hrm.menu_permissions import get_effective_menu_perm, user_can_access_menu
from hrm.module_permissions import MODULE_DE_XUAT, MODULE_KHO_NPL
from kho_npl.models import StockAdjustment
from service_requests.models import ServiceRequest
from service_requests.permissions import can_handle_step, can_view_request, pending_steps_for_user
from service_requests.models import ServiceRequestStep


def u(name):
    return User.objects.filter(username__iexact=name).select_related('profile').first()


def main():
    from hrm.concurrent_positions import (
        department_has_department_heads_extended,
        department_has_division_heads_extended,
        department_has_team_leaders_extended,
        effective_roles,
        find_manager_with_subordinate,
        get_active_concurrent_positions,
        heads_for_department,
    )
    from hrm.models import Department
    from hrm.permissions import ROLE_DEPARTMENT_HEAD, ROLE_DIVISION_HEAD, ROLE_TEAM_LEADER
    from service_requests.workflow import _needs_department_head_step, _needs_division_head_step, _needs_team_leader_step

    dinh = u('dinhgiang')
    duct = u('ductn')

    print('=== USERS ===')
    for label, x in (('dinhgiang', dinh), ('ductn', duct)):
        if not x:
            print(f'{label}: KHONG TON TAI')
            continue
        p = getattr(x, 'profile', None)
        dept = getattr(p, 'department', None)
        print(
            f'{x.username} id={x.id} role={getattr(p, "role", None)} '
            f'dept={dept.name if dept else None}({getattr(p, "department_id", None)}) '
            f'group={getattr(p, "permission_group_id", None)} '
            f'employed={getattr(p, "is_employed", None)}',
        )

    print('\n=== CẤU TRÚC PHÒNG MARKETING & KIÊM NHIỆM DUCTN ===')
    mkt = Department.objects.filter(name__icontains='marketing').first()
    if mkt:
        print(f'dept id={mkt.id} name={mkt.name}')
        print(f'  has_team_leader={department_has_team_leaders_extended(mkt)}')
        print(f'  has_division_head={department_has_division_heads_extended(mkt)}')
        print(f'  has_department_head={department_has_department_heads_extended(mkt)}')
        print('  heads_for_department:')
        for hp in heads_for_department(mkt.id):
            print(f'    {hp.user.username} role={hp.role} pos={hp.job_position!r}')
    if duct:
        print(f'ductn effective_roles={sorted(effective_roles(duct))}')
        for cp in get_active_concurrent_positions(duct.profile):
            print(
                f'  concurrent: dept={cp.department_id} div={cp.division_id} '
                f'role={cp.role} pos={cp.job_position!r} active={cp.is_active}',
            )
    if dinh and mkt:
        print('  managers for dinhgiang:')
        for role in (ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DEPARTMENT_HEAD):
            mgr = find_manager_with_subordinate(dinh, role)
            print(f'    {role}: {mgr.username if mgr else None}')
        print(f'  needs_tl={_needs_team_leader_step(dinh)}')
        print(f'  needs_div={_needs_division_head_step(dinh)}')
        print(f'  needs_dept={_needs_department_head_step(dinh)}')

    print('\n=== PHIẾU ĐIỀU CHỈNH (kho_npl) của dinhgiang ===')
    if dinh:
        adjs = StockAdjustment.objects.filter(proposed_by=dinh).select_related(
            'material', 'location',
        ).order_by('-created_at')
        print(f'count={adjs.count()}')
        for a in adjs[:10]:
            print(
                f'  {a.number} status={a.status} date={a.created_at.date()} '
                f'npl={a.material.code} loc={a.location.code}',
            )

    print('\n=== ductn — quyền kho_npl / phiếu điều chỉnh ===')
    if duct:
        for key in ('overview', 'materials', 'adjustments', 'stocktakes'):
            perm = get_effective_menu_perm(duct, MODULE_KHO_NPL, key)
            print(f'  {key}: access={user_can_access_menu(duct, MODULE_KHO_NPL, key)} perm={perm}')
        print(f'  tổng phiếu điều chỉnh DB: {StockAdjustment.objects.count()}')

    huu = u('huuchung')
    print('\n=== huuchung (đã duyệt phiếu #8) ===')
    if huu:
        p = getattr(huu, 'profile', None)
        print(
            f'{huu.username} role={getattr(p, "role", None)} '
            f'dept={getattr(p, "department_id", None)} div={getattr(p, "division_id", None)}',
        )
        if dinh:
            print(f'  subordinates has dinhgiang: {p.subordinates.filter(pk=dinh.pk).exists() if p else False}')
        for cp in get_active_concurrent_positions(huu.profile) if p else []:
            print(f'  concurrent: dept={cp.department_id} role={cp.role} pos={cp.job_position!r}')

    if duct and mkt:
        from hrm.models import ProfileConcurrentPosition

        slots = ProfileConcurrentPosition.objects.filter(
            profile=duct.profile, department_id=mkt.id,
        ).order_by('id')
        print('  ductn concurrent MKT slots history:')
        for cp in slots:
            print(
                f'    id={cp.id} active={cp.is_active} role={cp.role} '
                f'pos={cp.job_position!r}',
            )

    print('\n=== ĐỀ XUẤT (service_requests) của dinhgiang ===')
    if dinh:
        reqs = ServiceRequest.objects.filter(requester=dinh).prefetch_related('steps').order_by('-created_at')
        print(f'count={reqs.count()}')
        for r in reqs[:10]:
            print(
                f'  #{r.pk} [{r.request_type.code}] {r.title!r} status={r.status} '
                f'date={r.created_at.date()}',
            )
            for s in r.steps.order_by('step_order'):
                print(
                    f'    step{s.step_order} {s.step_code} status={s.status} '
                    f'assignee={getattr(s.assignee, "username", None)} '
                    f'dept_id={s.target_department_id} rule={s.assignee_rule}',
                )

    vananh = u('vananh')
    print('\n=== vananh — chờ xử lý đề xuất #8 ===')
    if vananh:
        p = getattr(vananh, 'profile', None)
        dept = getattr(p, 'department', None)
        print(
            f'{vananh.username} role={getattr(p, "role", None)} '
            f'dept={dept.name if dept else None}({getattr(p, "department_id", None)})',
        )
        pending_v = pending_steps_for_user(vananh).filter(request_id=8)
        print(f'pending request #8: {pending_v.count()}')
        for s in pending_v:
            print(f'  {s.step_code} status={s.status} handle={can_handle_step(vananh, s)}')

    print('\n=== ductn — quyền đề xuất / chờ xử lý ===')
    if duct:
        for key in ('my', 'pending', 'create'):
            print(f'  {key}: {user_can_access_menu(duct, MODULE_DE_XUAT, key)}')
        pending = pending_steps_for_user(duct)
        print(f'  pending_steps count={pending.count()}')
        for s in pending[:15]:
            print(
                f'    #{s.request.pk} step={s.step_code} status={s.status} '
                f'requester={s.request.requester.username} title={s.request.title!r}',
            )
        if dinh:
            print('  can_view_request / can_handle_step (đề xuất dinhgiang):')
            for r in ServiceRequest.objects.filter(requester=dinh).select_related(
                'request_type',
            ).order_by('-created_at')[:10]:
                print(
                    f'    #{r.pk}: view={can_view_request(duct, r)} '
                    f'cost={r.estimated_cost} tier={r.approval_tier}',
                )
                for s in r.steps.filter(
                    status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES,
                ).order_by('step_order'):
                    print(
                        f'      open step {s.step_code} status={s.status} '
                        f'handle={can_handle_step(duct, s)} assignee={getattr(s.assignee, "username", None)}',
                    )


if __name__ == '__main__':
    main()
