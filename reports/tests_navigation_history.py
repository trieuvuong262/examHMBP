from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.navigation import (
    history_url_for,
    list_back_url_for,
    team_list_back_url_for,
    team_list_query_from_request,
)
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

    def test_weekly_vp_redirects_to_unified_vp_report(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:weekly_vp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('period=week', resp.url)
        self.assertIn(reverse('reports:today_vp').rstrip('/'), resp.url)

    def test_my_reports_redirect_preserves_period(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:my'), {'period': 'weekly'})
        self.assertRedirects(
            resp,
            f'{reverse("reports:my_cn")}?period=weekly',
            fetch_redirect_response=False,
        )

    def test_history_url_for_office_weekly_includes_period(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        url = history_url_for(report, self.member)
        self.assertEqual(url, f'{reverse("reports:my_vp")}?period=week')

    def test_history_url_for_legacy_weekly_vp_includes_week_period(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        url = history_url_for(report, self.member)
        self.assertEqual(url, f'{reverse("reports:my_vp")}?period=week')

    def test_history_url_for_weekly_subordinate_includes_for_user(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        url = history_url_for(report, self.leader)
        self.assertEqual(
            url,
            f'{reverse("reports:my_vp")}?period=week&for_user={self.member.pk}',
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

    def test_team_list_back_url_preserves_filters(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        list_q = f'from={week.isoformat()}&to={week.isoformat()}&sort=member&dir=desc'
        url = team_list_back_url_for(
            report,
            self.leader,
            can_view_team=True,
            list_query=list_q,
        )
        self.assertEqual(url, f'{reverse("reports:team_vp")}?{list_q}')

    def test_detail_back_link_keeps_team_filters(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        list_q = f'from={week.isoformat()}&to={week.isoformat()}&sort=status'
        resp = self.client.get(
            reverse('reports:detail_vp', args=[report.pk]),
            {'from': week.isoformat(), 'to': week.isoformat(), 'sort': 'status'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:team_vp'))
        self.assertContains(resp, f'from={week.isoformat()}')
        self.assertContains(resp, 'sort=status')

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

    def test_my_vp_history_not_redirected_to_team_for_manager(self):
        """Tổ trưởng xem lịch sử cá nhân — không chuyển sang quản lý báo cáo."""
        group = PermissionGroup.objects.create(
            name='Leader VP only',
            slug='leader-vp-only-nav',
            module_permissions={
                'reports': {
                    'view': True,
                    'create': False,
                    'update': True,
                    'delete': False,
                    'export': True,
                    'menus': {
                        'daily_vp': {
                            'view': True, 'create': True, 'update': True, 'delete': False, 'export': False,
                        },
                        'daily_vp_detail': {
                            'view': True, 'create': False, 'update': True, 'delete': False, 'export': True,
                        },
                        'weekly_vp': {
                            'view': True, 'create': True, 'update': True, 'delete': False, 'export': False,
                        },
                    },
                },
            },
        )
        Profile.objects.filter(user=self.leader).update(permission_group=group)
        self.leader.refresh_from_db()
        self.client.force_login(self.leader)

        resp = self.client.get(reverse('reports:my_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Lịch sử báo cáo (VP)')
        self.assertContains(resp, reverse('reports:my_vp'))
        self.assertNotContains(resp, 'jp-reports-team-page')

    def test_my_url_for_user_prefers_daily_menu_over_detail(self):
        from reports.navigation import my_url_name_for_user

        group = PermissionGroup.objects.create(
            name='VP daily only',
            slug='vp-daily-only-nav',
            module_permissions={
                'reports': {
                    'view': True,
                    'create': True,
                    'update': False,
                    'delete': False,
                    'export': False,
                    'menus': {
                        'daily_vp': {
                            'view': True, 'create': True, 'update': False, 'delete': False, 'export': False,
                        },
                        'daily_vp_detail': {
                            'view': True, 'create': False, 'update': True, 'delete': False, 'export': False,
                        },
                    },
                },
            },
        )
        Profile.objects.filter(user=self.member).update(permission_group=group)
        self.member.refresh_from_db()
        self.assertEqual(my_url_name_for_user(self.member), 'reports:my_vp')

    def test_my_vp_resolves_to_daily_menu_not_detail(self):
        from hrm.menu_permissions import resolve_menu_from_request

        module, menu = resolve_menu_from_request('/reports/vp/my/')
        self.assertEqual(module, 'reports')
        self.assertIsNone(menu)

    def test_employee_with_daily_vp_only_can_open_history(self):
        group = PermissionGroup.objects.create(
            name='Employee VP daily',
            slug='employee-vp-daily-nav',
            module_permissions={
                'reports': {
                    'view': True,
                    'create': True,
                    'update': False,
                    'delete': False,
                    'export': False,
                    'menus': {
                        'daily_vp': {
                            'view': True, 'create': True, 'update': False, 'delete': False, 'export': False,
                        },
                    },
                },
            },
        )
        Profile.objects.filter(user=self.member).update(permission_group=group)
        self.member.refresh_from_db()
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:my_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Lịch sử báo cáo (VP)')
