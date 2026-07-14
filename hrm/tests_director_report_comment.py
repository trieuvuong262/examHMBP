"""Giam doc xem/nhan xet bao cao toan cong ty (SX + VP)."""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    can_comment_on_user_report,
    can_comment_on_user_weekly_report,
    can_review_user_report,
    can_view_team_reports,
    can_view_user_report,
    get_team_report_members,
)
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION


class DirectorCompanyWideReportCommentTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Dir Comment Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {
            'reports': {
                'view': True,
                'edit': True,
                'create': True,
                'update': True,
                'delete': False,
                'export': False,
            },
        }
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.outsider = self._user('outsider', ROLE_EMPLOYEE, dept)
        self.director = self._user('gm_comment', ROLE_DIRECTOR, dept)

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=dept,
            role=role,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_director_views_and_comments_non_subordinate_sx_and_vp(self):
        sx = DailyWorkReport.objects.create(
            employee=self.outsider,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_PRODUCTION,
            status=DailyWorkReport.STATUS_SUBMITTED,
        )
        vp = DailyWorkReport.objects.create(
            employee=self.outsider,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            shift='',
            status=DailyWorkReport.STATUS_SUBMITTED,
        )

        self.assertTrue(can_view_team_reports(self.director))
        self.assertTrue(get_team_report_members(self.director).filter(pk=self.outsider.pk).exists())
        self.assertTrue(can_view_user_report(self.director, sx))
        self.assertTrue(can_view_user_report(self.director, vp))

        self.assertFalse(can_review_user_report(self.director, sx))
        self.assertFalse(can_review_user_report(self.director, vp))

        self.assertTrue(can_comment_on_user_report(self.director, sx))
        self.assertTrue(can_comment_on_user_report(self.director, vp))

    def test_director_comments_weekly_non_subordinate(self):
        week = WeeklyWorkReport.objects.create(
            employee=self.outsider,
            week_start=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=WeeklyWorkReport.STATUS_SUBMITTED,
        )
        self.assertTrue(can_comment_on_user_weekly_report(self.director, week))
