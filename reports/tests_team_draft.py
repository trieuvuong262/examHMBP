from datetime import date, timedelta

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
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION
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
        resp = self.client.get(reverse('reports:team_cn'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ChÆ°a bÃ¡o cÃ¡o')
        self.assertNotContains(resp, 'NhÃ¡p')

    def test_saved_draft_shown_on_team_page(self):
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            status=DailyWorkReport.STATUS_DRAFT,
            draft_saved_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'))
        self.assertContains(resp, 'NhÃ¡p')

    def test_team_grouped_by_concurrent_department(self):
        mkt = Department.objects.create(name='MARKETING GRP', sort_order=2)
        sx = Department.objects.create(name='SAN XUAT GRP', sort_order=1, report_profile=REPORT_PROFILE_PRODUCTION)
        div = Division.objects.create(name='Team A', department=mkt, sort_order=1)
        mgr = self._user('mgr_grp', ROLE_EMPLOYEE, mkt)
        sub_mkt = self._user('sub_mkt', ROLE_EMPLOYEE, mkt)
        sub_sx = self._user('sub_sx', ROLE_EMPLOYEE, sx)
        slot_mkt = ProfileConcurrentPosition.objects.create(
            profile=mgr.profile,
            department=mkt,
            division=div,
            job_position='TrÆ°á»Ÿng bá»™ pháº­n',
            role=ROLE_DIVISION_HEAD,
        )
        slot_sx = ProfileConcurrentPosition.objects.create(
            profile=mgr.profile,
            department=sx,
            job_position='TrÆ°á»Ÿng phÃ²ng',
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
        resp = self.client.get(reverse('reports:team_cn'))
        self.assertContains(resp, 'SAN XUAT GRP')
        self.assertContains(resp, 'MARKETING GRP')

    def test_saved_weekly_draft_shown_on_team_page(self):
        week = monday_of(date.today())
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_DRAFT,
            draft_saved_at=timezone.now(),
            links='https://draft.example',
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_vp'), {
            'from': week.isoformat(),
            'to': (week + timedelta(days=6)).isoformat(),
        })
        self.assertContains(resp, 'NhÃ¡p')

    def test_unsaved_weekly_not_shown_as_draft_on_team_page(self):
        week = monday_of(date.today())
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_DRAFT,
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_vp'), {
            'from': week.isoformat(),
            'to': (week + timedelta(days=6)).isoformat(),
        })
        self.assertContains(resp, 'ChÆ°a bÃ¡o cÃ¡o')
        self.assertNotContains(resp, 'NhÃ¡p')

    def test_my_reports_lists_weekly_history(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://history.example',
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:my_vp'), {'period': 'week'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Tuáº§n')
        self.assertContains(resp, 'Link')
        self.assertContains(resp, 'ÄÃ£ ná»™p')
        self.assertContains(resp, reverse('reports:detail_vp', args=[report.pk]))

    def test_my_reports_hides_unsaved_weekly_draft(self):
        week = monday_of(date.today())
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_DRAFT,
        )
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:my_vp'), {'period': 'week'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ChÆ°a cÃ³ bÃ¡o cÃ¡o nÃ o')

    def test_team_weekly_vp_redirects_to_unified_team_page(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://example.com',
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_weekly_vp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('from=', resp.url)
        resp2 = self.client.get(reverse('reports:detail_vp', args=[report.pk]))
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, 'example.com')

    def test_team_stat_filter_submitted_and_missing(self):
        today = date.today()
        other = self._user('mem2_draft', ROLE_EMPLOYEE, self.member.profile.department)
        self.leader.profile.subordinates.add(other)
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=today,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        base = reverse('reports:team_cn') + f'?date={today.isoformat()}'

        resp_all = self.client.get(base)
        self.assertContains(resp_all, 'mem_draft')
        self.assertContains(resp_all, 'mem2_draft')

        resp_sub = self.client.get(base + '&status=submitted')
        self.assertContains(resp_sub, 'mem_draft')
        self.assertNotContains(resp_sub, 'mem2_draft')

        resp_miss = self.client.get(base + '&status=missing')
        self.assertNotContains(resp_miss, 'mem_draft')
        self.assertContains(resp_miss, 'mem2_draft')

    def test_team_vp_period_filter_week_only(self):
        today = date.today()
        week = monday_of(today)
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://week-only.example',
            submitted_at=timezone.now(),
        )
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=today,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='day',
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://day-only.example',
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_vp'), {
            'from': week.isoformat(),
            'to': today.isoformat(),
            'period': 'week',
        })
        self.assertEqual(resp.status_code, 200)
        week_report = DailyWorkReport.objects.get(employee=self.member, report_period='week')
        day_report = DailyWorkReport.objects.get(employee=self.member, report_period='day')
        self.assertContains(resp, reverse('reports:detail_vp', args=[week_report.pk]))
        self.assertNotContains(resp, reverse('reports:detail_vp', args=[day_report.pk]))

    def test_team_vp_shows_week_report_in_range(self):
        today = date.today()
        week = monday_of(today)
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://week.example',
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(
            reverse('reports:team_vp'),
            {
                'from': week.isoformat(),
                'to': today.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ÄÃ£ ná»™p')
        self.assertContains(resp, 'Tuáº§n')
        self.assertNotContains(resp, 'Nháº­p há»™')
        self.assertContains(resp, reverse('reports:detail_vp', args=[
            DailyWorkReport.objects.get(employee=self.member, report_period='week').pk,
        ]))

    def test_team_vp_excludes_production_subordinates(self):
        sx_dept = Department.objects.create(
            name='SX VP Exclude',
            sort_order=2,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        sx_member = self._user('mem_sx_vp', ROLE_EMPLOYEE, sx_dept)
        self.leader.profile.subordinates.add(sx_member)
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_vp'), {
            'from': date.today().isoformat(),
            'to': date.today().isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'mem_draft')
        self.assertNotContains(resp, 'mem_sx_vp')


