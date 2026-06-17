from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hrm.models import Department, Profile
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    build_hourly_grid,
    cumulative_quantity,
    ensure_active_work_block,
    ensure_work_day_started,
    finalize_product_with_metadata,
    pending_slots_for_report,
    save_hourly_entry,
    unfinalized_active_with_data,
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
        )

    def test_auto_start_and_active_block(self):
        ensure_work_day_started(self.report)
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.shift_started_at)
        self.assertEqual(self.report.shift, '')
        active = ensure_active_work_block(self.report)
        self.assertEqual(active.status, ProductionShiftProduct.STATUS_ACTIVE)
        self.assertEqual(active.product_code, '')

    def test_hourly_then_finalize(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        save_hourly_entry(product, 0, 120)
        save_hourly_entry(product, 1, 130)
        self.assertEqual(cumulative_quantity(product, 1), 250)

        finalized = finalize_product_with_metadata(
            self.report,
            product_code='PEGASUS',
            process_name='RÁP ĐÁY TRƯỚC x1',
            norm_per_hour=180,
        )
        self.assertEqual(finalized.product_code, 'PEGASUS')
        self.assertEqual(finalized.status, ProductionShiftProduct.STATUS_DONE)

        grid = build_hourly_grid(self.report)
        self.assertEqual(len(grid['rows']), 1)
        self.assertEqual(grid['rows'][0]['slots'][0]['quantity'], 120)
        self.assertEqual(grid['rows'][0]['slots'][1]['cumulative'], 250)
        self.assertEqual(grid['grand_total'], 250)

        new_active = ensure_active_work_block(self.report)
        self.assertNotEqual(new_active.pk, finalized.pk)
        self.assertEqual(new_active.product_code, '')

    def test_pending_slots(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
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

    def test_unfinalized_in_grid_before_finalize(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        save_hourly_entry(product, 0, 88)
        grid = build_hourly_grid(self.report)
        self.assertEqual(len(grid['rows']), 1)
        self.assertTrue(grid['has_unfinalized'])
        self.assertEqual(grid['grand_total'], 88)

    def test_unfinalized_detection(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        self.assertIsNone(unfinalized_active_with_data(self.report))
        save_hourly_entry(product, 0, 5)
        self.assertIsNotNone(unfinalized_active_with_data(self.report))
        finalize_product_with_metadata(
            self.report, product_code='A', process_name='X', norm_per_hour=10,
        )
        self.assertIsNone(unfinalized_active_with_data(self.report))
        self.assertEqual(ProductionHourlyQuantity.objects.filter(product=product).count(), 1)
