from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.report_lock import (
    can_edit_own_daily_report,
    can_edit_own_weekly_report,
    lock_report_on_supervisor_view,
)
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION
from reports.week_utils import monday_of


class ReportLockTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Lock Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )
        self.member = self._user('lock_member', ROLE_EMPLOYEE, dept)
        self.leader = self._user('lock_leader', ROLE_TEAM_LEADER, dept)
        self.leader.profile.subordinates.add(self.member)
        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=dept, role=role, full_name=username, is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_lock_daily_office_on_supervisor_view(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        with patch('hrm.permissions.can_view_user_report', return_value=True):
            self.assertTrue(lock_report_on_supervisor_view(report, self.leader))
        report.refresh_from_db()
        self.assertTrue(report.hod_reviewed)

    def test_lock_weekly_on_supervisor_view(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        with patch('hrm.permissions.can_view_user_weekly_report', return_value=True):
            self.assertTrue(lock_report_on_supervisor_view(report, self.leader))
        report.refresh_from_db()
        self.assertTrue(report.hod_reviewed)

    def test_employee_cannot_edit_locked_vp_daily(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            hod_reviewed=True,
            submitted_at=timezone.now(),
        )
        self.assertFalse(
            can_edit_own_daily_report(self.member, report, can_submit=True),
        )
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse('reports:today_vp'),
            {
                'report_date': report.report_date.isoformat(),
                'spreadsheet_data': '{}',
                'document_html': '<p>changed</p>',
                'action': 'save',
            },
        )
        self.assertRedirects(
            resp,
            f'{reverse("reports:today_vp")}?date={report.report_date.isoformat()}',
        )
        report.refresh_from_db()
        self.assertNotEqual(report.document_html, '<p>changed</p>')

    def test_employee_cannot_edit_locked_weekly_vp(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            hod_reviewed=True,
            links='https://original.example',
            submitted_at=timezone.now(),
        )
        self.assertFalse(
            can_edit_own_weekly_report(self.member, report, can_submit=True),
        )
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse('reports:weekly_vp'),
            {
                'week_start': week.isoformat(),
                'links': 'https://changed.example',
                'action': 'save',
            },
        )
        self.assertRedirects(
            resp,
            f'{reverse("reports:weekly_vp")}?week={week.isoformat()}',
        )
        report.refresh_from_db()
        self.assertEqual(report.links, 'https://original.example')

    def test_supervisor_view_detail_locks_vp_daily(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:detail_vp', args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        report.refresh_from_db()
        self.assertTrue(report.hod_reviewed)

    def test_locked_vp_daily_page_shows_message(self):
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            hod_reviewed=True,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.member)
        resp = self.client.get(reverse('reports:today_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Cấp trên đã xem báo cáo')
        self.assertNotContains(resp, 'Gửi Báo cáo')

    def test_lock_production_daily_still_works(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_PRODUCTION,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        self.client.get(reverse('reports:detail_cn', args=[report.pk]))
        report.refresh_from_db()
        self.assertTrue(report.hod_reviewed)
