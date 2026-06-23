from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    can_submit_daily_report,
    can_view_team_reports,
    get_report_team_users,
)
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION


class ReportHierarchyTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Xưởng Test', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])

        reports_perms = {
            'reports': {'view': True, 'edit': True},
        }
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': reports_perms},
            )

        self.employee = self._user('nv1', ROLE_EMPLOYEE, dept)
        self.leader = self._user('leader1', ROLE_TEAM_LEADER, dept)
        self.div_head = self._user('divhead1', ROLE_DIVISION_HEAD, dept)
        self.director = self._user('director1', ROLE_DIRECTOR, dept)
        self.outsider = self._user('nv2', ROLE_EMPLOYEE, dept)

        self.leader.profile.subordinates.set([self.employee])
        self.div_head.profile.subordinates.set([self.leader])
        self.director.profile.subordinates.set([self.div_head])

        self.report = DailyWorkReport.objects.create(
            employee=self.employee,
            report_date=date.today(),
            status=DailyWorkReport.STATUS_SUBMITTED,
        )

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=dept,
            role=role,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_team_users_only_manual_subordinates_from_hr(self):
        team = list(
            get_report_team_users(self.leader).values_list('username', flat=True),
        )
        self.assertEqual(team, ['nv1'])

        div_team = set(get_report_team_users(self.div_head).values_list('username', flat=True))
        self.assertEqual(div_team, {'leader1'})

        director_team = set(
            get_report_team_users(self.director).values_list('username', flat=True),
        )
        self.assertEqual(director_team, {'divhead1'})
        self.assertNotIn('nv1', director_team)
        self.assertNotIn('nv2', director_team)

        self.assertFalse(get_report_team_users(self.employee).exists())

    def test_director_cannot_submit_but_can_view_team(self):
        self.assertFalse(can_submit_daily_report(self.director))
        self.assertTrue(can_view_team_reports(self.director))

    def test_superuser_can_submit_despite_director_role(self):
        admin = User.objects.create_user(
            username='admin',
            password='testpass123',
            is_superuser=True,
        )
        Profile.objects.filter(user=admin).update(
            department=self.employee.profile.department,
            role=ROLE_DIRECTOR,
            full_name='Admin',
            is_employed=True,
        )
        admin.refresh_from_db()
        self.assertTrue(can_submit_daily_report(admin))

        client = Client()
        client.force_login(admin)
        resp = client.get(reverse('reports:today'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/today/', resp.url)

        resp_vp = client.get(reverse('reports:today_vp'))
        self.assertEqual(resp_vp.status_code, 200)

    def test_leader_can_submit_and_view_team(self):
        self.assertTrue(can_submit_daily_report(self.leader))
        self.assertTrue(can_view_team_reports(self.leader))

    def test_employee_can_submit_not_view_team(self):
        self.assertTrue(can_submit_daily_report(self.employee))
        self.assertFalse(can_view_team_reports(self.employee))

    def test_director_blocked_from_today_page(self):
        client = Client()
        client.force_login(self.director)
        resp = client.get(reverse('reports:today'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/reports/sx/team/', resp.url)

    def test_director_my_cn_redirects_to_team_missing(self):
        client = Client()
        client.force_login(self.director)
        resp = client.get(reverse('reports:my_cn'))
        self.assertRedirects(
            resp,
            f'{reverse("reports:team_cn")}?status=missing',
            fetch_redirect_response=False,
        )

    def test_leader_sees_only_direct_subordinate_report(self):
        client = Client()
        client.force_login(self.leader)
        resp = client.get(reverse('reports:detail_cn', args=[self.report.pk]))
        self.assertEqual(resp.status_code, 200)

        client.force_login(self.div_head)
        resp = client.get(reverse('reports:detail_cn', args=[self.report.pk]))
        self.assertEqual(resp.status_code, 302)

        leader_report = DailyWorkReport.objects.create(
            employee=self.leader,
            report_date=date.today(),
            status=DailyWorkReport.STATUS_SUBMITTED,
        )
        client.force_login(self.div_head)
        resp = client.get(reverse('reports:detail_cn', args=[leader_report.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_outsider_cannot_view_report(self):
        client = Client()
        client.force_login(self.outsider)
        resp = client.get(reverse('reports:detail_cn', args=[self.report.pk]))
        self.assertEqual(resp.status_code, 302)


class ReportProfileRoutingTests(TestCase):
    def setUp(self):
        self.prod_dept = Department.objects.create(
            name='Xưởng SX Test',
            sort_order=901,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        self.office_dept = Department.objects.create(
            name='Phòng HC Test',
            sort_order=902,
            report_profile=REPORT_PROFILE_OFFICE,
        )
        for dept in (self.prod_dept, self.office_dept):
            DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        reports_perms = {'reports': {'view': True, 'edit': True}}
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': reports_perms},
        )
        self.prod_user = self._user('sx_nv', self.prod_dept)
        self.office_user = self._user('hcns_nv', self.office_dept)

    def _user(self, username, dept):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_production_user_sees_production_form(self):
        client = Client()
        client.force_login(self.prod_user)
        resp = client.get(reverse('reports:today_cn'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/today_production_hourly.html')

    def test_office_user_sees_office_form(self):
        client = Client()
        client.force_login(self.office_user)
        resp = client.get(reverse('reports:today_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/today_office.html')
        self.assertContains(resp, 'Bảng')
        self.assertContains(resp, 'Văn bản')

    def test_daily_page_shows_vp_title_and_period_tabs(self):
        client = Client()
        client.force_login(self.office_user)
        resp = client.get(reverse('reports:today_vp'))
        self.assertContains(resp, 'Báo cáo VP')
        self.assertContains(resp, 'jp-office-page-hero')
        self.assertNotContains(resp, 'Mỗi dòng một link')
        self.assertContains(resp, 'Ngày')
        self.assertContains(resp, 'Tuần')
        self.assertContains(resp, 'Tháng')

    def test_weekly_report_routed_by_scope(self):
        client = Client()
        client.force_login(self.prod_user)
        resp = client.get(reverse('reports:weekly_cn'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/reports/sx/', resp.url)

        client.force_login(self.office_user)
        resp = client.get(reverse('reports:weekly_vp'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/reports/vp/', resp.url)
        self.assertIn('period=week', resp.url)

    def test_legacy_weekly_url_redirects(self):
        client = Client()
        client.force_login(self.prod_user)
        resp = client.get(reverse('reports:weekly'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/reports/sx/weekly/', resp.url)
