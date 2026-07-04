"""Tests for production team view (consolidated by day)."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport
from reports.production_team import (
    build_production_team_department_groups,
    build_production_week_rollup,
    production_team_submitted_count,
)
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION
from reports.team_utils import daily_report_visible_to_team
from reports.week_utils import monday_of


class ProductionTeamViewTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(
            name='SX Team Shift',
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.leader = self._user('ldr_shift', ROLE_TEAM_LEADER, dept)
        self.member = self._user('mem_shift', ROLE_EMPLOYEE, dept)
        self.other = self._user('mem_none', ROLE_EMPLOYEE, dept)
        self.leader.profile.subordinates.add(self.member, self.other)
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

    def _morning_report(self, *, employee=None, report_date=None, status=DailyWorkReport.STATUS_SUBMITTED, draft_saved=False):
        return DailyWorkReport.objects.create(
            employee=employee or self.member,
            report_date=report_date or self.today,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period='day',
            shift=DailyWorkReport.SHIFT_MORNING,
            status=status,
            draft_saved_at=timezone.now() if draft_saved or status == DailyWorkReport.STATUS_SUBMITTED else None,
            shift_started_at=timezone.now(),
        )

    def test_team_merges_shifts_on_same_day(self):
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
        resp = self.client.get(reverse('reports:team_cn'), {
            'from': self.today.isoformat(),
            'to': self.today.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '2 b\u00e1o c\u00e1o')

    def test_team_shows_employee_without_reports(self):
        self._morning_report()
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {
            'from': self.today.isoformat(),
            'to': self.today.isoformat(),
        })
        self.assertContains(resp, 'mem_none')
        self.assertContains(resp, 'Ch\u01b0a b\u00e1o c\u00e1o')

    def test_team_splits_rows_by_day_and_shows_missing_days(self):
        yesterday = self.today - timedelta(days=1)
        self._morning_report(report_date=yesterday)
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {
            'from': yesterday.isoformat(),
            'to': self.today.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, yesterday.strftime('%d/%m/%Y'))
        self.assertContains(resp, self.today.strftime('%d/%m/%Y'))

    def test_build_groups_one_row_per_day_in_range(self):
        yesterday = self.today - timedelta(days=1)
        reports_by_employee = {
            self.member.id: [
                self._morning_report(report_date=yesterday),
                self._morning_report(),
                DailyWorkReport.objects.create(
                    employee=self.member,
                    report_date=self.today,
                    report_profile=REPORT_PROFILE_PRODUCTION,
                    report_period='day',
                    shift=DailyWorkReport.SHIFT_OVERTIME,
                    status=DailyWorkReport.STATUS_DRAFT,
                    draft_saved_at=timezone.now(),
                    shift_started_at=timezone.now(),
                ),
            ],
        }
        team = User.objects.filter(pk__in=[self.member.pk, self.other.pk])
        groups, _ = build_production_team_department_groups(
            self.leader,
            team,
            reports_by_employee,
            daily_report_visible_to_team,
            date_from=yesterday,
            date_to=self.today,
        )
        member_rows = [row for group in groups for row in group['rows'] if row['member'].id == self.member.id]
        other_rows = [row for group in groups for row in group['rows'] if row['member'].id == self.other.id]
        self.assertEqual(len(member_rows), 2)
        self.assertEqual(member_rows[0]['production_report_count'], 2)
        self.assertEqual(len(other_rows), 1)
        self.assertIsNone(other_rows[0]['report_date'])

    def test_team_single_report_links_to_detail(self):
        report = self._morning_report()
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {
            'from': self.today.isoformat(),
            'to': self.today.isoformat(),
        })
        self.assertContains(resp, reverse('reports:detail_cn', args=[report.pk]))

    def test_team_excludes_non_production_subordinates(self):
        vp_dept = Department.objects.create(
            name='VP Test',
            sort_order=2,
            report_profile=REPORT_PROFILE_OFFICE,
        )
        vp_member = self._user('mem_vp', ROLE_EMPLOYEE, vp_dept)
        self.leader.profile.subordinates.add(vp_member)
        self._morning_report()
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_cn'), {
            'from': self.today.isoformat(),
            'to': self.today.isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'mem_shift')
        self.assertNotContains(resp, 'mem_vp')

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

    def test_submitted_count_any_shift_in_range(self):
        reports_by_employee = {
            self.member.id: [self._morning_report()],
        }
        submitted, missing = production_team_submitted_count(
            reports_by_employee,
            daily_report_visible_to_team,
            team_count=2,
        )
        self.assertEqual(submitted, 1)
        self.assertEqual(missing, 1)

    def test_team_total_qty_from_production_hourly_entries(self):
        from decimal import Decimal

        from reports.models import ProductionHourlyQuantity, ProductionShiftProduct
        from reports.production_team import query_production_team_reports

        report = self._morning_report(draft_saved=True)
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code='TEST',
            process_name='May',
            norm_per_hour=Decimal('100'),
            status=ProductionShiftProduct.STATUS_DONE,
            sort_order=0,
        )
        ProductionHourlyQuantity.objects.create(
            product=product,
            slot_index=0,
            quantity=Decimal('120'),
        )
        ProductionHourlyQuantity.objects.create(
            product=product,
            slot_index=1,
            quantity=Decimal('80'),
        )
        qs = query_production_team_reports([self.member.id], self.today, self.today)
        annotated = qs.get(pk=report.pk)
        self.assertEqual(annotated.total_qty, Decimal('200'))

    def test_status_counts_split_draft_and_no_report(self):
        from reports.production_team import production_team_status_counts

        reports_by_employee = {
            self.member.id: [
                self._morning_report(status=DailyWorkReport.STATUS_DRAFT, draft_saved=True),
            ],
        }
        counts = production_team_status_counts(
            [self.member.id, self.other.id],
            reports_by_employee,
            daily_report_visible_to_team,
        )
        self.assertEqual(counts['submitted'], 0)
        self.assertEqual(counts['draft_saved'], 1)
        self.assertEqual(counts['no_report'], 1)
