from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    can_view_team_reports,
    can_view_user_report,
    get_report_team_users,
    get_team_report_members,
    is_global_report_viewer,
)
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.production_hourly import can_edit_production_report
from reports.report_lock import (
    can_edit_own_daily_report,
    can_edit_own_weekly_report,
    is_report_edit_expired,
    last_editable_date,
    lock_report_on_supervisor_view,
)
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION
from reports.week_utils import monday_of


class ReportLockTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Lock Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIRECTOR):
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
            f'{reverse("reports:today_vp")}?period=day&date={report.report_date.isoformat()}',
        )
        report.refresh_from_db()
        self.assertNotEqual(report.document_html, '<p>changed</p>')

    def test_employee_cannot_edit_locked_weekly_vp(self):
        week = monday_of(date.today())
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            hod_reviewed=True,
            links='https://original.example',
            submitted_at=timezone.now(),
        )
        self.assertFalse(
            can_edit_own_daily_report(self.member, report, can_submit=True),
        )
        self.client.force_login(self.member)
        resp = self.client.post(
            reverse('reports:today_vp'),
            {
                'period': 'week',
                'report_date': week.isoformat(),
                'links': 'https://changed.example',
                'action': 'save',
            },
        )
        self.assertRedirects(
            resp,
            f'{reverse("reports:today_vp")}?period=week&date={week.isoformat()}',
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

    def test_can_edit_until_end_of_day_after_report(self):
        report_date = date(2026, 1, 10)
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=report_date,
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.assertEqual(last_editable_date(report), date(2026, 1, 11))
        with patch('reports.report_lock.timezone.localdate', return_value=date(2026, 1, 11)):
            self.assertFalse(is_report_edit_expired(report))
            self.assertTrue(can_edit_own_daily_report(self.member, report, can_submit=True))
        with patch('reports.report_lock.timezone.localdate', return_value=date(2026, 1, 12)):
            self.assertTrue(is_report_edit_expired(report))
            self.assertFalse(can_edit_own_daily_report(self.member, report, can_submit=True))

    def test_week_vp_edit_window_uses_week_end(self):
        week = date(2026, 1, 5)
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.assertEqual(last_editable_date(report), date(2026, 1, 12))
        with patch('reports.report_lock.timezone.localdate', return_value=date(2026, 1, 12)):
            self.assertFalse(is_report_edit_expired(report))
        with patch('reports.report_lock.timezone.localdate', return_value=date(2026, 1, 13)):
            self.assertTrue(is_report_edit_expired(report))

    def test_production_daily_respects_edit_window(self):
        report_date = date(2026, 3, 1)
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        with patch('reports.report_lock.timezone.localdate', return_value=date(2026, 3, 3)):
            self.assertFalse(
                can_edit_production_report(self.member, report, can_submit=True),
            )

    def test_expired_vp_page_shows_message(self):
        report_date = date(2026, 1, 10)
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=report_date,
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.member)
        with patch('reports.report_lock.timezone.localdate', return_value=date(2026, 1, 12)):
            resp = self.client.get(
                reverse('reports:today_vp'),
                {'date': report_date.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Đã quá hạn chỉnh sửa')
        self.assertContains(resp, '11/01/2026')


class GlobalReportViewerTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Global Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )
        self.member = User.objects.create_user(username='global_member', password='test')
        Profile.objects.filter(user=self.member).update(
            department=dept, role=ROLE_EMPLOYEE, full_name='Member', is_employed=True,
        )
        self.member.refresh_from_db()
        self.overseer = User.objects.create_user(username='ductn', password='test')
        Profile.objects.filter(user=self.overseer).update(
            department=dept, role=ROLE_DIRECTOR, full_name='Overseer', is_employed=True,
        )
        self.overseer.refresh_from_db()
        self.client = Client(HTTP_HOST='testserver')

    def test_global_viewer_can_view_any_report(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.assertTrue(is_global_report_viewer(self.overseer))
        self.assertTrue(can_view_user_report(self.overseer, report))
        self.assertFalse(
            get_report_team_users(self.overseer).filter(pk=self.member.pk).exists(),
        )
        self.assertTrue(
            get_team_report_members(self.overseer).filter(pk=self.member.pk).exists(),
        )

    def test_global_viewer_view_does_not_lock_report(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.overseer)
        resp = self.client.get(reverse('reports:detail_vp', args=[report.pk]))
        self.assertEqual(resp.status_code, 200)
        report.refresh_from_db()
        self.assertFalse(report.hod_reviewed)

    def test_global_viewer_weekly_view_does_not_lock(self):
        week = monday_of(date.today())
        report = WeeklyWorkReport.objects.create(
            employee=self.member,
            week_start=week,
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.assertFalse(lock_report_on_supervisor_view(report, self.overseer))
        report.refresh_from_db()
        self.assertFalse(report.hod_reviewed)

    def test_global_viewer_can_open_team_reports(self):
        self.assertTrue(can_view_team_reports(self.overseer))

    def test_global_viewer_locks_direct_subordinate_report(self):
        self.overseer.profile.subordinates.add(self.member)
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.assertTrue(lock_report_on_supervisor_view(report, self.overseer))
        report.refresh_from_db()
        self.assertTrue(report.hod_reviewed)
        self.client.force_login(self.overseer)
        report.hod_reviewed = False
        report.save(update_fields=['hod_reviewed'])
        self.client.get(reverse('reports:detail_vp', args=[report.pk]))
        report.refresh_from_db()
        self.assertTrue(report.hod_reviewed)
