"""Tests for production team view (shift-aware)."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport
from reports.production_team import (
    build_production_week_rollup,
    production_team_submitted_count,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.team_utils import daily_report_visible_to_team
from reports.week_utils import monday_of


class ProductionTeamViewTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='SX Team Shift', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.leader = self._user('ldr_shift', ROLE_TEAM_LEADER, dept)
        self.member = self._user('mem_shift', ROLE_EMPLOYEE, dept)
        self.leader.profile.subordinates.add(self.member)
        self.client = Client(HTTP_HOST='testserver')
        self.today = date.today()

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

    def _morning_report(self, *, status=DailyWorkReport.STATUS_SUBMITTED, draft_saved=False):
        return DailyWorkReport.objects.create(
            employee=self.member,
            report_date=self.today,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period='day',
            shift=DailyWorkReport.SHIFT_MORNING,
            status=status,
            draft_saved_at=timezone.now() if draft_saved or status == DailyWorkReport.STATUS_SUBMITTED else None,
            shift_started_at=timezone.now(),
        )

    def test_team_shows_all_shift_cells(self):
        self._morning_report()
        DailyWorkReport.objects.create(
            employee=self.member,
            report_date=self.today,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period='day',
            shift=DailyWorkReport.SHIFT_OVERTIME,
            status=DailyWorkReport.STATUS_DRAFT,
            draft_saved_at=timezone.now(),
            shift_started_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {'date': self.today.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ca sáng')
        self.assertContains(resp, 'Tăng ca')
        self.assertContains(resp, 'Ca tối')
        self.assertContains(resp, 'Theo ca')

    def test_team_shift_filter_morning(self):
        self._morning_report()
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {
            'date': self.today.isoformat(),
            'shift': DailyWorkReport.SHIFT_MORNING,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Đã nộp')
        self.assertNotContains(resp, 'Theo ca')

    def test_team_shift_stats_cards(self):
        self._morning_report()
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {'date': self.today.isoformat()})
        self.assertContains(resp, 'jp-team-shift-stat-grid')

    def test_week_rollup_warns_missing_morning_days(self):
        week_start = monday_of(self.today)
        for offset in range(2):
            DailyWorkReport.objects.create(
                employee=self.member,
                report_date=week_start + timedelta(days=offset),
                report_profile=REPORT_PROFILE_PRODUCTION,
                report_period='day',
                shift=DailyWorkReport.SHIFT_MORNING,
                status=DailyWorkReport.STATUS_SUBMITTED,
                submitted_at=timezone.now(),
                shift_started_at=timezone.now(),
            )
        rollup = build_production_week_rollup(
            [self.member.id],
            self.today,
            daily_report_visible_to_team,
        )
        self.assertIn(self.member.id, rollup)
        self.assertGreater(rollup[self.member.id]['missing_days'], 0)
        self.assertIn('Thiếu', rollup[self.member.id]['warning'])

    def test_submitted_count_per_shift(self):
        reports_by_employee = {
            self.member.id: {
                DailyWorkReport.SHIFT_MORNING: self._morning_report(),
            },
        }
        submitted, missing = production_team_submitted_count(
            reports_by_employee,
            daily_report_visible_to_team,
            shift_filter=DailyWorkReport.SHIFT_MORNING,
            team_count=1,
        )
        self.assertEqual(submitted, 1)
        self.assertEqual(missing, 0)

        submitted_ot, missing_ot = production_team_submitted_count(
            reports_by_employee,
            daily_report_visible_to_team,
            shift_filter=DailyWorkReport.SHIFT_OVERTIME,
            team_count=1,
        )
        self.assertEqual(submitted_ot, 0)
        self.assertEqual(missing_ot, 1)
