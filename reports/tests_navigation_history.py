from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.navigation import history_url_for, list_back_url_for
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION
from reports.week_utils import monday_of


class ReportHistoryNavigationTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Nav Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )
        self.member = self._user('nav_member', ROLE_EMPLOYEE, dept)
        self.leader = self._user('nav_leader', ROLE_TEAM_LEADER, dept)
        self.leader.profile.subordinates.add(self.member)
        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=dept, role=role, full_name=username, is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_today_vp_history_links_to_my_vp(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:today_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:my_vp'))
        self.assertNotContains(resp, reverse('reports:my'))

    def test_today_cn_history_links_to_my_cn(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:today_cn'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:my_cn'))

    def test_weekly_vp_history_links_with_period(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:weekly_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'{reverse("reports:my_vp")}?period=weekly')

    def test_my_reports_redirect_preserves_period(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:my'), {'period': 'weekly'})
        self.assertRedirects(
            resp,
            f'{reverse("reports:my_cn")}?period=weekly',
            fetch_redirect_response=False,
        )

    def test_history_url_for_weekly_includes_period(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        url = history_url_for(report, self.member)
        self.assertEqual(url, f'{reverse("reports:my_vp")}?period=weekly')

    def test_history_url_for_weekly_subordinate_includes_for_user(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        url = history_url_for(report, self.leader)
        self.assertEqual(
            url,
            f'{reverse("reports:my_vp")}?period=weekly&for_user={self.member.pk}',
        )

    def test_list_back_url_for_own_weekly_includes_period(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_PRODUCTION,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        url = list_back_url_for(report, self.member, can_view_team=False)
        self.assertEqual(url, f'{reverse("reports:my_cn")}?period=weekly')

    def test_today_vp_team_link_uses_team_vp(self):
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:today_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:team_vp'))

    def test_daily_detail_history_uses_profile_scope(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:detail_vp', args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:my_vp'))
