from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hrm.models import Department, Profile
from hrm.permissions import ROLE_EMPLOYEE
from reports.models import (
    DailyWorkReport,
    DailyWorkReportEditLog,
    ProductionHourlyQuantity,
    ProductionReportReminderLog,
    ProductionShiftProduct,
)
from reports.production_report_reminders import (
    DEFAULT_DECLARED_WORK_HOURS,
    auto_submit_one_report,
    auto_submit_unsubmitted_production_reports,
    can_auto_submit_report,
    is_auto_submit_window,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION


class ProductionReportAutoSubmitTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='SX AutoSubmit',
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        self.user = User.objects.create_user(username='sx_auto', password='x')
        Profile.objects.filter(user=self.user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='SX Auto',
            is_employed=True,
        )
        self.user.refresh_from_db()
        self.report_date = timezone.localdate() - timedelta(days=1)

    def _report(self, *, shift=DailyWorkReport.SHIFT_MORNING, status=DailyWorkReport.STATUS_DRAFT):
        return DailyWorkReport.objects.create(
            employee=self.user,
            report_date=self.report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=shift,
            status=status,
            shift_started_at=timezone.now() - timedelta(hours=8),
        )

    def _add_done_product(self, report, qty=10):
        start = timezone.make_aware(datetime.combine(
            self.report_date, datetime.min.time().replace(hour=8, minute=0),
        ))
        end = start + timedelta(hours=2)
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code='SP1',
            process_name='May',
            norm_per_hour=Decimal('10'),
            sort_order=0,
            first_slot_index=0,
            status=ProductionShiftProduct.STATUS_DONE,
            started_at=start,
            ended_at=end,
            total_quantity=Decimal(str(qty)),
        )
        ProductionHourlyQuantity.objects.create(
            product=product,
            slot_index=0,
            quantity=Decimal(str(qty)),
        )
        return product

    def test_window_1130(self):
        day = timezone.localdate()
        inside = timezone.make_aware(datetime.combine(
            day, datetime.min.time().replace(hour=11, minute=32),
        ))
        outside = timezone.make_aware(datetime.combine(
            day, datetime.min.time().replace(hour=12, minute=0),
        ))
        self.assertTrue(is_auto_submit_window(now=inside))
        self.assertFalse(is_auto_submit_window(now=outside))

    def test_skip_night_shift(self):
        report = self._report(shift=DailyWorkReport.SHIFT_NIGHT)
        self._add_done_product(report)
        ok, reason = can_auto_submit_report(report)
        self.assertFalse(ok)
        self.assertEqual(reason, 'night_shift')

    def test_auto_submit_sets_default_hours(self):
        report = self._report()
        self._add_done_product(report)
        result = auto_submit_one_report(report)
        self.assertEqual(result, 'submitted')
        report.refresh_from_db()
        self.assertEqual(report.status, DailyWorkReport.STATUS_SUBMITTED)
        self.assertTrue(report.auto_submitted)
        self.assertEqual(report.declared_work_hours, DEFAULT_DECLARED_WORK_HOURS)
        self.assertTrue(
            DailyWorkReportEditLog.objects.filter(
                report=report,
                action=DailyWorkReportEditLog.ACTION_SUBMIT,
            ).exists()
        )
        self.assertTrue(
            ProductionReportReminderLog.objects.filter(
                employee=self.user,
                report_date=self.report_date,
                shift=DailyWorkReport.SHIFT_MORNING,
            ).exists()
        )

    def test_keeps_existing_declared_hours(self):
        report = self._report()
        report.declared_work_hours = Decimal('10.00')
        report.save(update_fields=['declared_work_hours'])
        self._add_done_product(report)
        auto_submit_one_report(report)
        report.refresh_from_db()
        self.assertEqual(report.declared_work_hours, Decimal('10.00'))

    def test_batch_force_yesterday(self):
        report = self._report()
        self._add_done_product(report)
        night = self._report(shift=DailyWorkReport.SHIFT_NIGHT)
        self._add_done_product(night, qty=5)
        stats = auto_submit_unsubmitted_production_reports(
            force=True,
            report_date=self.report_date,
        )
        self.assertEqual(stats['submitted'], 1)
        report.refresh_from_db()
        night.refresh_from_db()
        self.assertEqual(report.status, DailyWorkReport.STATUS_SUBMITTED)
        self.assertEqual(night.status, DailyWorkReport.STATUS_DRAFT)

    def test_skip_empty_report(self):
        report = self._report()
        ok, reason = can_auto_submit_report(report)
        self.assertFalse(ok)
        self.assertEqual(reason, 'no_quantity')
