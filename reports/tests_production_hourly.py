"""Tests for production hourly report logic."""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile
from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    active_product,
    build_hourly_grid,
    build_proxy_entry_grid,
    build_productivity_report,
    can_edit_production_report,
    cumulative_quantity,
    ensure_active_work_block,
    ensure_work_day_started,
    finalize_product_with_metadata,
    is_production_report_locked,
    lock_production_report_on_supervisor_view,
    pending_slots_for_report,
    save_hourly_entry,
    unfinalized_active_with_data,
    update_product_norms,
)
from reports.production_slots import (
    MORNING_SLOTS,
    OVERTIME_SLOTS,
    NIGHT_SLOTS,
    PRODUCTION_HOURLY_SLOTS,
    SLOT_COUNT,
    current_slot_index,
    due_slot_indices,
    slot_count_for_shift,
)
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
        DepartmentMenuPermission.objects.get_or_create(
            department=self.dept,
            defaults={'modules': ['reports']},
        )
        self.user = User.objects.create_user(username='worker1', password='x')
        Profile.objects.filter(user=self.user).update(
            full_name='Công nhân A',
            department=self.dept,
            is_employed=True,
        )
        self.report_date = timezone.localdate()
        self.report = DailyWorkReport.objects.create(
            employee=self.user,
            report_date=self.report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=DailyWorkReport.SHIFT_MORNING,
        )

    def test_auto_start_and_active_block(self):
        self.report.shift = DailyWorkReport.SHIFT_MORNING
        ensure_work_day_started(self.report)
        self.report.refresh_from_db()
        self.assertIsNotNone(self.report.shift_started_at)
        self.assertEqual(self.report.shift, DailyWorkReport.SHIFT_MORNING)
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

        new_active = active_product(self.report)
        self.assertNotEqual(new_active.pk, finalized.pk)
        self.assertEqual(new_active.product_code, '')
        self.assertEqual(new_active.first_slot_index, 2)

    def test_pegasus_thor_slot_scope(self):
        """Mã mới chỉ nhập từ khung sau mã trước — Thor không nhập được 7h30."""
        ensure_work_day_started(self.report)
        pegasus = ensure_active_work_block(self.report)
        save_hourly_entry(pegasus, 0, 100)
        save_hourly_entry(pegasus, 1, 100)
        save_hourly_entry(pegasus, 2, 100)
        finalize_product_with_metadata(
            self.report,
            product_code='PEGASUS',
            process_name='May áo',
            norm_per_hour=100,
        )
        thor = active_product(self.report)
        self.assertEqual(thor.first_slot_index, 3)

        with self.assertRaises(ValueError):
            save_hourly_entry(thor, 0, 105)

        save_hourly_entry(thor, 3, 105)
        noon = timezone.make_aware(datetime.combine(self.report_date, time(11, 0)))
        pending = pending_slots_for_report(self.report, now=noon)
        self.assertTrue(all(p['slot_index'] >= 3 for p in pending))

        grid = build_hourly_grid(self.report)
        thor_row = next(r for r in grid['rows'] if r['id'] == thor.pk)
        self.assertTrue(thor_row['slots'][0]['is_na'])
        self.assertTrue(thor_row['slots'][2]['is_na'])

    def test_zero_quantity_requires_reason(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        with self.assertRaises(ValueError):
            save_hourly_entry(product, 0, 0)
        save_hourly_entry(product, 0, 0, zero_reason='Bận việc khác')
        entry = product.hourly_entries.get(slot_index=0)
        self.assertEqual(entry.quantity, 0)
        self.assertEqual(entry.zero_reason, 'Bận việc khác')
        fake_now = timezone.make_aware(datetime.combine(self.report_date, time(9, 0)))
        pending = pending_slots_for_report(self.report, now=fake_now)
        self.assertEqual(pending[0]['slot_index'], 1)

    def test_damaged_quantity_and_note(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        save_hourly_entry(
            product, 0, 120,
            damaged_quantity=3,
            note='Lỗi đường may',
        )
        entry = product.hourly_entries.get(slot_index=0)
        self.assertEqual(entry.damaged_quantity, 3)
        self.assertEqual(entry.note, 'Lỗi đường may')

        grid = build_hourly_grid(self.report)
        cell = grid['rows'][0]['slots'][0]
        self.assertEqual(cell['damaged_quantity'], 3)
        self.assertEqual(cell['note'], 'Lỗi đường may')

        prod = build_productivity_report(self.report)
        row = prod['hourly_rows'][0]
        self.assertEqual(row['damaged_quantity'], 3)
        self.assertEqual(row['note'], 'Lỗi đường may')

        save_hourly_entry(product, 1, 50, damaged_quantity=2, note='')
        entry2 = product.hourly_entries.get(slot_index=1)
        self.assertEqual(entry2.damaged_quantity, 2)
        self.assertEqual(entry2.note, '')

        save_hourly_entry(product, 0, 100, note='Cập nhật')
        entry.refresh_from_db()
        self.assertEqual(entry.quantity, 100)
        self.assertEqual(entry.damaged_quantity, 3)
        self.assertEqual(entry.note, 'Cập nhật')

    def test_pending_slots(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        fake_now = timezone.make_aware(datetime.combine(self.report_date, time(10, 0)))
        pending = pending_slots_for_report(self.report, now=fake_now)
        self.assertTrue(len(pending) >= 2)
        save_hourly_entry(product, 0, 50)
        pending2 = pending_slots_for_report(self.report, now=fake_now)
        self.assertEqual(pending2[0]['slot_index'], 1)

    def test_slot_helpers_morning(self):
        self.assertEqual(SLOT_COUNT, 9)
        self.assertEqual(len(MORNING_SLOTS), 9)
        self.assertEqual(PRODUCTION_HOURLY_SLOTS[0].start, time(7, 30))
        self.assertEqual(MORNING_SLOTS[-1].end, time(18, 0))
        noon = timezone.make_aware(datetime.combine(self.report_date, time(11, 0)))
        self.assertEqual(
            current_slot_index(noon, self.report_date, DailyWorkReport.SHIFT_MORNING),
            3,
        )
        due = due_slot_indices(noon, self.report_date, DailyWorkReport.SHIFT_MORNING)
        self.assertIn(3, due)
        evening = timezone.make_aware(datetime.combine(self.report_date, time(20, 30)))
        self.assertIsNone(
            current_slot_index(evening, self.report_date, DailyWorkReport.SHIFT_MORNING),
        )
        self.assertEqual(
            due_slot_indices(evening, self.report_date, DailyWorkReport.SHIFT_MORNING),
            list(range(9)),
        )

    def test_slot_helpers_overtime(self):
        self.assertEqual(slot_count_for_shift(DailyWorkReport.SHIFT_OVERTIME), 4)
        self.assertEqual(OVERTIME_SLOTS[-1].end, time(22, 0))
        at_20 = timezone.make_aware(datetime.combine(self.report_date, time(20, 15)))
        self.assertEqual(
            current_slot_index(at_20, self.report_date, DailyWorkReport.SHIFT_OVERTIME),
            2,
        )

    def test_slot_helpers_night_crosses_midnight(self):
        self.assertEqual(slot_count_for_shift(DailyWorkReport.SHIFT_NIGHT), 11)
        evening = timezone.make_aware(datetime.combine(self.report_date, time(20, 0)))
        self.assertEqual(
            current_slot_index(evening, self.report_date, DailyWorkReport.SHIFT_NIGHT),
            2,
        )
        after_midnight = timezone.make_aware(
            datetime.combine(self.report_date + timedelta(days=1), time(2, 30))
        )
        self.assertEqual(
            current_slot_index(after_midnight, self.report_date, DailyWorkReport.SHIFT_NIGHT),
            8,
        )
        after_shift = timezone.make_aware(
            datetime.combine(self.report_date + timedelta(days=1), time(6, 0))
        )
        self.assertIsNone(
            current_slot_index(after_shift, self.report_date, DailyWorkReport.SHIFT_NIGHT),
        )
        self.assertEqual(
            due_slot_indices(after_shift, self.report_date, DailyWorkReport.SHIFT_NIGHT),
            list(range(11)),
        )

    def test_overtime_grid_has_four_slots(self):
        self.report.shift = DailyWorkReport.SHIFT_OVERTIME
        self.report.save(update_fields=['shift'])
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        save_hourly_entry(product, 0, 10)
        grid = build_hourly_grid(self.report)
        self.assertEqual(len(grid['slots']), 4)
        self.assertEqual(grid['slots'][-1]['label'], '21h - 22h')

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

    def test_submitted_employee_can_edit_until_locked(self):
        self.report.status = DailyWorkReport.STATUS_SUBMITTED
        self.report.save(update_fields=['status'])
        self.assertTrue(
            can_edit_production_report(self.user, self.report, can_submit=True),
        )
        self.report.hod_reviewed = True
        self.report.save(update_fields=['hod_reviewed'])
        self.assertFalse(
            can_edit_production_report(self.user, self.report, can_submit=True),
        )
        self.assertTrue(is_production_report_locked(self.report))

    def test_supervisor_view_locks_submitted_report(self):
        leader = User.objects.create_user(username='leader1', password='x')
        self.report.status = DailyWorkReport.STATUS_SUBMITTED
        self.report.save(update_fields=['status'])

        with patch(
            'hrm.permissions.can_view_user_report',
            return_value=True,
        ):
            locked = lock_production_report_on_supervisor_view(self.report, leader)
        self.assertTrue(locked)
        self.report.refresh_from_db()
        self.assertTrue(self.report.hod_reviewed)

        with patch(
            'hrm.permissions.can_view_user_report',
            return_value=False,
        ):
            self.assertFalse(lock_production_report_on_supervisor_view(self.report, self.user))

    def test_productivity_report_hourly(self):
        ensure_work_day_started(self.report)
        pegasus = ensure_active_work_block(self.report)
        save_hourly_entry(pegasus, 0, 100)
        save_hourly_entry(pegasus, 1, 100)
        save_hourly_entry(pegasus, 2, 100)
        finalize_product_with_metadata(
            self.report,
            product_code='PEGASUS',
            process_name='May áo pegasus',
            norm_per_hour=100,
        )
        thor = active_product(self.report)
        save_hourly_entry(thor, 3, 105)
        finalize_product_with_metadata(
            self.report,
            product_code='THOR',
            process_name='May áo thor',
            norm_per_hour=105,
        )

        prod = build_productivity_report(self.report)
        self.assertTrue(prod['has_data'])
        self.assertEqual(len(prod['hourly_rows']), 4)
        self.assertEqual(prod['hourly_rows'][0]['product_code'], 'PEGASUS')
        self.assertEqual(prod['hourly_rows'][0]['slot_label'], '7h30 - 8h30')
        self.assertEqual(prod['hourly_rows'][3]['product_code'], 'THOR')
        self.assertEqual(prod['hourly_rows'][0]['efficiency_pct'], 100.0)
        self.assertEqual(prod['total_quantity'], 405)
        self.assertEqual(prod['overall_efficiency_pct'], 100.0)
        self.assertEqual(len(prod['product_summaries']), 2)
        self.assertEqual(prod['product_summaries'][0]['efficiency_pct'], 100.0)

    def test_productivity_rows_sorted_by_product(self):
        ensure_work_day_started(self.report)
        product_a = ensure_active_work_block(self.report)
        save_hourly_entry(product_a, 0, 50)
        save_hourly_entry(product_a, 1, 50)
        finalize_product_with_metadata(
            self.report,
            product_code='ALPHA',
            process_name='Op A',
            norm_per_hour=50,
        )
        product_b = active_product(self.report)
        save_hourly_entry(product_b, 2, 40)
        save_hourly_entry(product_b, 3, 40)
        finalize_product_with_metadata(
            self.report,
            product_code='BETA',
            process_name='Op B',
            norm_per_hour=40,
        )

        prod = build_productivity_report(self.report)
        codes = [row['product_code'] for row in prod['hourly_rows']]
        self.assertEqual(codes, ['ALPHA', 'ALPHA', 'BETA', 'BETA'])

    def test_update_product_norms(self):
        ensure_work_day_started(self.report)
        product = ensure_active_work_block(self.report)
        save_hourly_entry(product, 0, 90)
        finalize_product_with_metadata(
            self.report,
            product_code='PEGASUS',
            process_name='May áo',
            norm_per_hour=100,
        )
        product = self.report.production_products.get(product_code='PEGASUS')

        count = update_product_norms(self.report, {product.id: 90})
        self.assertEqual(count, 1)
        product.refresh_from_db()
        self.assertEqual(product.norm_per_hour, 90)

        prod = build_productivity_report(self.report)
        self.assertEqual(prod['product_summaries'][0]['norm_per_hour'], 90.0)
        self.assertEqual(prod['product_summaries'][0]['efficiency_pct'], 100.0)
        grid = build_hourly_grid(self.report)
        self.assertEqual(grid['rows'][0]['norm_per_hour'], 90.0)

    def test_proxy_entry_grid_all_slots_editable(self):
        ensure_work_day_started(self.report)
        ensure_active_work_block(self.report)
        grid = build_proxy_entry_grid(self.report)
        self.assertTrue(grid['proxy_mode'])
        self.assertEqual(len(grid['rows']), 1)
        row = grid['rows'][0]
        self.assertEqual(len(row['slots']), slot_count_for_shift(DailyWorkReport.SHIFT_MORNING))
        self.assertTrue(all(not cell['is_na'] for cell in row['slots']))

    def test_proxy_save_relaxes_slot_scope(self):
        ensure_work_day_started(self.report)
        pegasus = ensure_active_work_block(self.report)
        save_hourly_entry(pegasus, 0, 100)
        finalize_product_with_metadata(
            self.report,
            product_code='PEGASUS',
            process_name='May',
            norm_per_hour=100,
        )
        thor = active_product(self.report)
        save_hourly_entry(thor, 3, 50, relax_slot_scope=True)
        self.assertEqual(thor.hourly_entries.get(slot_index=3).quantity, 50)

    def test_pending_slots_ignore_time(self):
        ensure_work_day_started(self.report)
        ensure_active_work_block(self.report)
        with patch('reports.production_hourly.due_slot_indices', return_value=[]):
            pending = pending_slots_for_report(self.report)
            self.assertEqual(pending, [])
            pending_proxy = pending_slots_for_report(
                self.report,
                ignore_time_constraints=True,
            )
            self.assertEqual(
                len(pending_proxy),
                slot_count_for_shift(DailyWorkReport.SHIFT_MORNING),
            )


class ProductionShiftPolicyTests(TestCase):
    def setUp(self):
        from hrm.models import DepartmentMenuPermission
        from hrm.models import RoleModulePermission
        from hrm.permissions import ROLE_EMPLOYEE

        self.dept, _ = Department.objects.get_or_create(
            name='SX Shift Policy',
            defaults={'report_profile': REPORT_PROFILE_PRODUCTION},
        )
        DepartmentMenuPermission.objects.get_or_create(
            department=self.dept,
            defaults={'modules': ['reports']},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'reports': {'view': True, 'create': True}}},
        )
        self.user = User.objects.create_user(username='shift_worker', password='x')
        Profile.objects.filter(user=self.user).update(
            full_name='Shift Worker',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.client = Client()
        self.report_date = timezone.localdate()

    def test_overtime_requires_morning(self):
        from reports.production_shift_policy import can_start_production_shift

        ok, reason = can_start_production_shift(
            self.user, self.report_date, DailyWorkReport.SHIFT_OVERTIME,
        )
        self.assertFalse(ok)
        self.assertIn('ca sáng', reason.lower())

        DailyWorkReport.objects.create(
            employee=self.user,
            report_date=self.report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=DailyWorkReport.SHIFT_MORNING,
        )
        ok, _ = can_start_production_shift(
            self.user, self.report_date, DailyWorkReport.SHIFT_OVERTIME,
        )
        self.assertTrue(ok)

    def test_night_excludes_morning_same_day(self):
        from reports.production_shift_policy import can_start_production_shift

        DailyWorkReport.objects.create(
            employee=self.user,
            report_date=self.report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=DailyWorkReport.SHIFT_MORNING,
        )
        ok, reason = can_start_production_shift(
            self.user, self.report_date, DailyWorkReport.SHIFT_NIGHT,
        )
        self.assertFalse(ok)
        self.assertIn('ca tối', reason.lower())

    def test_shift_picker_overtime_blocked_without_morning(self):
        from reports.production_shift_policy import build_shift_picker_options

        options = build_shift_picker_options(self.user, self.report_date, can_edit=True)
        overtime = next(o for o in options if o['shift'] == DailyWorkReport.SHIFT_OVERTIME)
        self.assertEqual(overtime['action'], 'blocked')
        self.assertFalse(overtime['enabled'])
