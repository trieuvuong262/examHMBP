"""Thống kê báo cáo — menu KPI cho HR (không cần cấp dưới)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.group_permissions import normalize_group_permissions
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.permissions import (
    ROLE_EMPLOYEE,
    can_view_report_statistics,
    can_view_team_reports,
    has_company_wide_report_access,
)
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_team import (
    SUMMARY_METRIC_QUANTITY,
    SUMMARY_METRIC_TIME,
    build_production_team_summary,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION


class ReportStatisticsAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='HR Stats Dept',
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['reports'])
        perms = normalize_group_permissions({
            'reports': {
                'view': True,
                'create': False,
                'update': False,
                'delete': False,
                'export': True,
                'menus': {
                    'report_stats': {
                        'view': True,
                        'create': False,
                        'update': False,
                        'delete': False,
                        'export': True,
                    },
                },
            },
        })
        self.group = PermissionGroup.objects.create(
            slug='test-report-stats-hr',
            name='HR Report Stats',
            module_permissions=perms,
        )
        self.hr = User.objects.create_user(username='hr_stats', password='test')
        Profile.objects.filter(user=self.hr).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group,
            full_name='HR Stats',
            is_employed=True,
        )
        self.hr.refresh_from_db()

        self.worker = User.objects.create_user(username='sx_worker', password='test')
        Profile.objects.filter(user=self.worker).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='SX Worker',
            is_employed=True,
        )
        self.worker.refresh_from_db()
        self.client = Client(HTTP_HOST='testserver')

    def test_hr_without_subordinates_can_open_stats(self):
        self.assertTrue(can_view_report_statistics(self.hr))
        self.assertTrue(has_company_wide_report_access(self.hr))
        self.assertTrue(can_view_team_reports(self.hr))

        self.client.force_login(self.hr)
        resp = self.client.get(reverse('reports:report_stats_cn'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Thống kê báo cáo')
        self.assertContains(resp, 'Hiệu suất theo thời gian')
        self.assertContains(resp, 'Sản lượng')

    def test_employee_without_menu_cannot_open_stats(self):
        other = User.objects.create_user(username='no_stats', password='test')
        Profile.objects.filter(user=other).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        other.refresh_from_db()
        self.assertFalse(can_view_report_statistics(other))
        self.client.force_login(other)
        resp = self.client.get(reverse('reports:report_stats_cn'))
        self.assertEqual(resp.status_code, 302)


class ReportStatisticsMetricTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='SX Metric Dept',
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        self.viewer = User.objects.create_user(username='metric_viewer', password='test')
        Profile.objects.filter(user=self.viewer).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='Viewer',
            is_employed=True,
        )
        self.viewer.refresh_from_db()
        self.member = User.objects.create_user(username='metric_member', password='test')
        Profile.objects.filter(user=self.member).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='Member',
            is_employed=True,
        )
        self.member.refresh_from_db()
        self.day = date.today()

    def _make_report(self, *, quantity=Decimal('100'), declared_hours=Decimal('8')):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=self.day,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=DailyWorkReport.SHIFT_MORNING,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
            declared_work_hours=declared_hours,
            shift_started_at=timezone.now(),
        )
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code='SP01',
            process_name='May',
            norm_per_hour=Decimal('10'),
            sort_order=1,
            total_quantity=quantity,
            started_at=timezone.now() - timedelta(hours=5),
            ended_at=timezone.now(),
        )
        ProductionHourlyQuantity.objects.create(
            product=product,
            slot_index=0,
            quantity=quantity,
            partial_hours=Decimal('5'),
        )
        return report

    def test_quantity_metric_sums_production(self):
        report = self._make_report(quantity=Decimal('50'))
        summary = build_production_team_summary(
            self.viewer,
            User.objects.filter(pk=self.member.pk),
            {self.member.pk: [report]},
            lambda r: True,
            date_from=self.day,
            date_to=self.day,
            metric=SUMMARY_METRIC_QUANTITY,
        )
        self.assertFalse(summary['metric_is_percent'])
        member_row = summary['groups'][0]['members'][0]
        self.assertEqual(member_row['avg_value'], 50.0)
        self.assertTrue(member_row['cells'][0]['has_data'])

    def test_time_metric_uses_declared_hours(self):
        report = self._make_report(quantity=Decimal('50'), declared_hours=Decimal('8'))
        summary = build_production_team_summary(
            self.viewer,
            User.objects.filter(pk=self.member.pk),
            {self.member.pk: [report]},
            lambda r: True,
            date_from=self.day,
            date_to=self.day,
            metric=SUMMARY_METRIC_TIME,
        )
        self.assertTrue(summary['metric_is_percent'])
        member_row = summary['groups'][0]['members'][0]
        self.assertEqual(member_row['avg_value'], 62.5)

