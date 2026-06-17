from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hrm.models import Department, Profile
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    build_hourly_grid,
    cumulative_quantity,
    pending_slots_for_report,
    save_hourly_entry,
    start_product_session,
    start_production_shift,
)
from reports.production_slots import SLOT_COUNT, current_slot_index, due_slot_indices
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()


class ProductionHourlyTests(TestCase):
    def setUp(self):
        self.dept, _ = Department.objects.get_or_create(
            name='SX Test Hourly',
            defaults={'report_profile': REPORT_PROFILE_PRODUCTION},
        )
        if self.dept.report_profile != REPORT_PROFILE_PRODUCTION:
            self.dept.report_profile = REPORT_PROFILE_PRODUCTION
            self.dept.save(update_fields=['report_profile'])
        self.user = User.objects.create_user(username='worker1', password='x')
        Profile.objects.filter(user=self.user).update(
            full_name='Công nhân A',
            department=self.dept,
        )
        self.report_date = date(2026, 6, 16)
        self.report = DailyWorkReport.objects.create(
            employee=self.user,
            report_date=self.report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=DailyWorkReport.SHIFT_MORNING,
        )

    def test_start_shift_and_product(self):
        start_production_shift(self.report, DailyWorkReport.SHIFT_MORNING)
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.shift_started_at)

        product = start_product_session(
            self.report,
            product_code='PEGASUS',
            process_name='RÁP ĐÁY TRƯỚC x1',
            norm_per_hour=180,
        )
        self.assertEqual(product.product_code, 'PEGASUS')
        self.assertEqual(product.status, ProductionShiftProduct.STATUS_ACTIVE)

    def test_hourly_cumulative(self):
        start_production_shift(self.report, DailyWorkReport.SHIFT_MORNING)
        product = start_product_session(
            self.report,
            product_code='PEGASUS',
            process_name='RÁP ĐÁY TRƯỚC x1',
            norm_per_hour=180,
        )
        save_hourly_entry(product, 0, 120)
        save_hourly_entry(product, 1, 130)
        self.assertEqual(cumulative_quantity(product, 0), 120)
        self.assertEqual(cumulative_quantity(product, 1), 250)

        grid = build_hourly_grid(self.report)
        self.assertEqual(len(grid['rows']), 1)
        self.assertEqual(grid['rows'][0]['slots'][0]['quantity'], 120)
        self.assertEqual(grid['rows'][0]['slots'][0]['cumulative'], 120)
        self.assertEqual(grid['rows'][0]['slots'][1]['cumulative'], 250)
        self.assertEqual(grid['grand_total'], 250)

    def test_pending_slots(self):
        start_production_shift(self.report, DailyWorkReport.SHIFT_MORNING)
        product = start_product_session(
            self.report,
            product_code='PEGASUS',
            process_name='TEST',
            norm_per_hour=100,
        )
        fake_now = timezone.make_aware(datetime.combine(self.report_date, time(10, 0)))
        pending = pending_slots_for_report(self.report, now=fake_now)
        self.assertTrue(len(pending) >= 2)
        save_hourly_entry(product, 0, 50)
        pending2 = pending_slots_for_report(self.report, now=fake_now)
        self.assertEqual(pending2[0]['slot_index'], 1)

    def test_slot_helpers(self):
        self.assertEqual(SLOT_COUNT, 8)
        noon = timezone.make_aware(datetime.combine(self.report_date, time(11, 0)))
        self.assertEqual(current_slot_index(noon, self.report_date), 3)
        due = due_slot_indices(noon, self.report_date)
        self.assertIn(3, due)

    def test_end_product_starts_new(self):
        start_production_shift(self.report, DailyWorkReport.SHIFT_MORNING)
        p1 = start_product_session(
            self.report, product_code='A', process_name='X', norm_per_hour=10,
        )
        save_hourly_entry(p1, 0, 5)
        p2 = start_product_session(
            self.report, product_code='B', process_name='Y', norm_per_hour=20,
        )
        p1.refresh_from_db()
        self.assertEqual(p1.status, ProductionShiftProduct.STATUS_DONE)
        self.assertEqual(p2.product_code, 'B')
        self.assertEqual(ProductionHourlyQuantity.objects.filter(product=p1).count(), 1)
