"""Smoke phiếu giấy SX — chạy: docker compose exec -T web python manage.py shell < scripts/_smoke_proxy_paper_sheet.py"""

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER, get_team_report_members
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()


def _ensure_role_perms():
    perms = {
        'reports': {'view': True, 'edit': True, 'create': True, 'update': True},
    }
    for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER):
        RoleModulePermission.objects.update_or_create(
            role=role,
            defaults={'module_permissions': perms},
        )


def main():
    leader = None
    worker = None
    worker2 = None
    for cand in User.objects.filter(is_active=True).select_related('profile').order_by('id'):
        members = list(
            get_team_report_members(cand)
            .filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION)[:2]
        )
        if members:
            leader = cand
            worker = members[0]
            worker2 = members[1] if len(members) > 1 else members[0]
            break

    if leader is None or worker is None:
        _ensure_role_perms()
        dept, _ = Department.objects.get_or_create(
            name='SX Smoke Paper',
            defaults={'report_profile': REPORT_PROFILE_PRODUCTION, 'sort_order': 9901},
        )
        if dept.report_profile != REPORT_PROFILE_PRODUCTION:
            dept.report_profile = REPORT_PROFILE_PRODUCTION
            dept.save(update_fields=['report_profile'])
        DepartmentMenuPermission.objects.get_or_create(
            department=dept,
            defaults={'modules': ['reports']},
        )
        leader, _ = User.objects.get_or_create(username='smoke_paper_leader')
        if not leader.has_usable_password():
            leader.set_password('test')
            leader.save()
        Profile.objects.filter(user=leader).update(
            department=dept,
            role=ROLE_TEAM_LEADER,
            full_name='Smoke Leader',
            is_employed=True,
        )
        leader.refresh_from_db()
        worker, _ = User.objects.get_or_create(username='smoke_paper_worker')
        if not worker.has_usable_password():
            worker.set_password('test')
            worker.save()
        Profile.objects.filter(user=worker).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Smoke Worker',
            is_employed=True,
            employee_code='SMK001',
        )
        worker.refresh_from_db()
        leader.profile.subordinates.add(worker)
        worker2 = worker

    today = timezone.localdate()
    client = Client()
    client.force_login(leader)

    url_select = reverse('reports:proxy_paper_sheet') + f'?date={today.isoformat()}&shift=MORNING'
    r0 = client.get(url_select, HTTP_HOST='localhost')
    html0 = r0.content.decode('utf-8', errors='replace')
    assert r0.status_code == 200, r0.status_code
    assert 'In phiếu giấy SX' in html0 or 'Chọn công nhân' in html0
    assert 'jp-paper-user' in html0 or 'name="for_user"' in html0

    url_one = (
        reverse('reports:proxy_paper_sheet')
        + f'?date={today.isoformat()}&shift=NIGHT&for_user={worker.pk}'
    )
    if worker2 and worker2.pk != worker.pk:
        url_one += f'&for_user={worker2.pk}'
    r2 = client.get(url_one, HTTP_HOST='localhost')
    html2 = r2.content.decode('utf-8', errors='replace')
    assert r2.status_code == 200, (r2.status_code, html2[:300])
    assert 'Báo cáo sản xuất hàng ngày' in html2
    worker_name = worker.profile.full_name or worker.username
    assert worker_name in html2
    assert f'for_user={worker.pk}' in html2

    print('SMOKE_OK', {
        'leader': leader.username,
        'worker': worker.username,
        'select_status': r0.status_code,
        'print_status': r2.status_code,
    })


main()
