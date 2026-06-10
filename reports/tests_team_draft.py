from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import (
    Department,
    DepartmentMenuPermission,
    Division,
    Profile,
    ProfileConcurrentPosition,
    RoleModulePermission,
)
from hrm.permissions import ROLE_DIRECTOR, ROLE_DIVISION_HEAD, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.team_utils import build_report_team_department_groups
from reports.week_utils import monday_of


class ReportTeamDraftTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Draft Team Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.leader = self._user('ldr_draft', ROLE_TEAM_LEADER, dept)
        self.member = self._user('mem_draft', ROLE_EMPLOYEE, dept)
        self.leader.profile.subordinates.add(self.member)
        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=dept, role=role, full_name=username, is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_unsaved_daily_not_shown_as_draft_on_team_page(self):
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            status=DailyWorkReport.STATUS_DRAFT,
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Chưa báo cáo')
        self.assertNotContains(resp, 'Nháp')

    def test_saved_draft_shown_on_team_page(self):
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            status=DailyWorkReport.STATUS_DRAFT,
            draft_saved_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team'))
        self.assertContains(resp, 'Nháp')

    def test_team_grouped_by_concurrent_department(self):
        mkt = Department.objects.create(name='MARKETING GRP', sort_order=2)
        sx = Department.objects.create(name='SAN XUAT GRP', sort_order=1)
        div = Division.objects.create(name='Team A', department=mkt, sort_order=1)
        mgr = self._user('mgr_grp', ROLE_EMPLOYEE, mkt)
        sub_mkt = self._user('sub_mkt', ROLE_EMPLOYEE, mkt)
        sub_sx = self._user('sub_sx', ROLE_EMPLOYEE, sx)
        slot_mkt = ProfileConcurrentPosition.objects.create(
            profile=mgr.profile,
            department=mkt,
            division=div,
            job_position='Trưởng bộ phận',
            role=ROLE_DIVISION_HEAD,
        )
        slot_sx = ProfileConcurrentPosition.objects.create(
            profile=mgr.profile,
            department=sx,
            job_position='Trưởng phòng',
            role=ROLE_DIVISION_HEAD,
        )
        slot_mkt.subordinates.add(sub_mkt)
        slot_sx.subordinates.add(sub_sx)

        from hrm.permissions import get_report_team_users
        team = get_report_team_users(mgr)
        groups = build_report_team_department_groups(mgr, team)
        labels = [g['label'] for g in groups]
        self.assertEqual(labels, ['SAN XUAT GRP', 'MARKETING GRP'])
        self.assertEqual(len(groups[0]['members']), 1)
        self.assertEqual(groups[0]['members'][0].username, 'sub_sx')

        self.client.force_login(mgr)
        resp = self.client.get(reverse('reports:team'))
        self.assertContains(resp, 'SAN XUAT GRP')
        self.assertContains(resp, 'MARKETING GRP')

    def test_team_weekly_page_loads_for_leader(self):
        week = monday_of(date.today())
        WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            links='https://example.com',
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_weekly'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Báo cáo tuần')
        resp2 = self.client.get(reverse('reports:weekly_detail', args=[
            WeeklyWorkReport.objects.get(employee=self.member, week_start=week).pk,
        ]))
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, 'jp-weekly-link-card')
        self.assertContains(resp2, 'example.com')
        self.assertContains(resp2, 'Chi tiết báo cáo tuần')
