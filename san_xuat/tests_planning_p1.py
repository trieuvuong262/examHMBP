"""Test P1 — nền tảng lập kế hoạch sản xuất: lịch làm việc, năng lực bottleneck,
phân tổ, truyền tổ sang LSX, giữ chỗ NPL, vòng đời kế hoạch.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from san_xuat.hub_models import (
    SxDetailPlan,
    SxGeneralSettings,
    SxHoliday,
    SxMaterialPlan,
    SxOverallPlan,
    SxWorkCenter,
)
from san_xuat.services.planning import (
    PlanningError,
    add_overall_plan_line,
    assign_detail_plan_work_centers,
    cancel_plan,
    check_detail_plan_capacity,
    close_plan,
    confirm_detail_plan,
    confirm_overall_plan,
    create_overall_plan,
    detail_plan_progress,
    explode_detail_plan_from_overall,
    resolve_daily_capacity,
)
from san_xuat.services.work_calendar import (
    normalize_workdays,
    working_day_count,
    working_days,
)


def _settings(**kwargs):
    cfg = SxGeneralSettings.load()
    for key, val in kwargs.items():
        setattr(cfg, key, val)
    cfg.save()
    return cfg


class WorkCalendarTests(TestCase):
    def test_normalize_workdays_fallback(self):
        self.assertEqual(normalize_workdays('1111110'), '1111110')
        self.assertEqual(normalize_workdays(''), '1111110')
        self.assertEqual(normalize_workdays('abc'), '1111110')
        self.assertEqual(normalize_workdays('0000000'), '1111110')
        self.assertEqual(normalize_workdays('1111100'), '1111100')

    def test_sunday_excluded_by_default(self):
        # 03/08/2026 là Thứ 2 → 09/08/2026 là Chủ nhật
        monday = date(2026, 8, 3)
        days = working_days(monday, monday + timedelta(days=6))
        self.assertEqual(len(days), 6)
        self.assertNotIn(date(2026, 8, 9), days)

    def test_holiday_excluded(self):
        SxHoliday.objects.create(holiday_date=date(2026, 8, 5), name='Nghỉ thử')
        days = working_days(date(2026, 8, 3), date(2026, 8, 8))
        self.assertEqual(len(days), 5)
        self.assertNotIn(date(2026, 8, 5), days)

    def test_saturday_off_config(self):
        _settings(plan_workdays='1111100')
        self.assertEqual(working_day_count(date(2026, 8, 3), date(2026, 8, 9)), 5)


class CapacityModeTests(TestCase):
    def setUp(self):
        SxWorkCenter.objects.create(code='T-CUT', name='Cắt', capacity_per_day=Decimal('300'))
        SxWorkCenter.objects.create(code='T-PRINT', name='In', capacity_per_day=Decimal('240'))
        SxWorkCenter.objects.create(code='T-SEW', name='May', capacity_per_day=Decimal('322'))
        # Tổ không hoạt động và tổ NL=0 không được tính
        SxWorkCenter.objects.create(
            code='T-OFF', name='Tắt', capacity_per_day=Decimal('999'), is_active=False,
        )
        SxWorkCenter.objects.create(code='T-ZERO', name='Cơ điện', capacity_per_day=Decimal('0'))

    def test_bottleneck_is_default(self):
        cap = resolve_daily_capacity()
        self.assertEqual(cap.mode, SxGeneralSettings.CAP_MODE_BOTTLENECK)
        self.assertEqual(cap.capacity, Decimal('240'))
        self.assertEqual(cap.bottleneck_label, 'In')
        self.assertEqual(cap.center_count, 3)

    def test_total_mode(self):
        _settings(plan_capacity_mode=SxGeneralSettings.CAP_MODE_TOTAL)
        cap = resolve_daily_capacity()
        self.assertEqual(cap.capacity, Decimal('862'))

    def test_no_center_returns_zero(self):
        SxWorkCenter.objects.all().delete()
        self.assertEqual(resolve_daily_capacity().capacity, Decimal('0'))


class DetailPlanAllocationTests(TestCase):
    def setUp(self):
        SxWorkCenter.objects.create(code='T-CUT', name='Cắt', capacity_per_day=Decimal('300'))
        SxWorkCenter.objects.create(code='T-PRINT', name='In', capacity_per_day=Decimal('240'))
        self.plan = create_overall_plan(
            name='KH test',
            date_from=date(2026, 8, 3),   # Thứ 2
            date_to=date(2026, 8, 9),     # Chủ nhật
        )
        add_overall_plan_line(
            plan_id=self.plan.pk, product_code='SP-TEST', qty_planned=Decimal('600'),
        )
        confirm_overall_plan(plan_id=self.plan.pk)

    def test_no_qty_on_sunday(self):
        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        dates = {ln.plan_date for ln in detail.lines.all()}
        self.assertEqual(len(dates), 6, 'Phải bỏ Chủ nhật')
        self.assertNotIn(date(2026, 8, 9), dates)
        total = sum((ln.qty for ln in detail.lines.all()), Decimal('0'))
        self.assertEqual(total, Decimal('600'), 'Tổng phân bổ phải bằng SL kế hoạch')

    def test_refresh_keeps_assigned_teams(self):
        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        assign_detail_plan_work_centers(plan_id=detail.pk)
        before = {
            (ln.product_code, ln.plan_date): ln.team_label for ln in detail.lines.all()
        }
        self.assertTrue(all(before.values()), 'Phải gán tổ hết')

        explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        detail.refresh_from_db()
        after = {
            (ln.product_code, ln.plan_date): ln.team_label for ln in detail.lines.all()
        }
        self.assertEqual(before, after, 'Refresh không được mất tổ đã gán')

    def test_assign_skips_already_assigned_unless_overwrite(self):
        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        first = assign_detail_plan_work_centers(plan_id=detail.pk)
        self.assertEqual(first, 6)
        self.assertEqual(assign_detail_plan_work_centers(plan_id=detail.pk), 0)
        self.assertEqual(
            assign_detail_plan_work_centers(plan_id=detail.pk, overwrite=True), 6,
        )

    def test_block_over_capacity_by_default(self):
        # 600 / 6 ngày = 100/ngày < 240 → không vượt
        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        self.assertEqual(check_detail_plan_capacity(plan_id=detail.pk), [])
        confirm_detail_plan(plan_id=detail.pk)
        detail.refresh_from_db()
        self.assertEqual(detail.status, SxOverallPlan.STATUS_CONFIRMED)

    def test_over_capacity_raises(self):
        big = create_overall_plan(
            name='KH lớn', date_from=date(2026, 8, 3), date_to=date(2026, 8, 4),
        )
        add_overall_plan_line(
            plan_id=big.pk, product_code='SP-BIG', qty_planned=Decimal('2000'),
        )
        confirm_overall_plan(plan_id=big.pk)
        detail = explode_detail_plan_from_overall(overall_plan_id=big.pk)
        warns = check_detail_plan_capacity(plan_id=detail.pk)
        self.assertEqual(len(warns), 2, '1000/ngày > 240 → cả 2 ngày vượt')
        with self.assertRaises(PlanningError):
            confirm_detail_plan(plan_id=detail.pk)

    def test_over_capacity_allowed_when_setting_off(self):
        _settings(plan_block_over_capacity=False)
        big = create_overall_plan(
            name='KH lớn 2', date_from=date(2026, 8, 3), date_to=date(2026, 8, 4),
        )
        add_overall_plan_line(
            plan_id=big.pk, product_code='SP-BIG2', qty_planned=Decimal('2000'),
        )
        confirm_overall_plan(plan_id=big.pk)
        detail = explode_detail_plan_from_overall(overall_plan_id=big.pk)
        confirm_detail_plan(plan_id=detail.pk)
        detail.refresh_from_db()
        self.assertEqual(detail.status, SxOverallPlan.STATUS_CONFIRMED)
        self.assertIn('vượt năng lực', detail.notes)

    def test_period_without_working_day_raises(self):
        sunday_only = create_overall_plan(
            name='Chỉ CN', date_from=date(2026, 8, 9), date_to=date(2026, 8, 9),
        )
        add_overall_plan_line(
            plan_id=sunday_only.pk, product_code='SP-X', qty_planned=Decimal('10'),
        )
        confirm_overall_plan(plan_id=sunday_only.pk)
        with self.assertRaises(PlanningError):
            explode_detail_plan_from_overall(overall_plan_id=sunday_only.pk)


class PlanLifecycleTests(TestCase):
    def setUp(self):
        SxWorkCenter.objects.create(code='T1', name='Tổ 1', capacity_per_day=Decimal('500'))
        self.plan = create_overall_plan(
            name='KH vòng đời', date_from=date(2026, 8, 3), date_to=date(2026, 8, 5),
        )
        add_overall_plan_line(
            plan_id=self.plan.pk, product_code='SP-LC', qty_planned=Decimal('300'),
        )
        confirm_overall_plan(plan_id=self.plan.pk)

    def test_close_requires_confirmed(self):
        draft = create_overall_plan(
            name='Nháp', date_from=date(2026, 8, 3), date_to=date(2026, 8, 3),
        )
        with self.assertRaises(PlanningError):
            close_plan(model=SxOverallPlan, plan_id=draft.pk)

    def test_close_and_cancel(self):
        closed = close_plan(model=SxOverallPlan, plan_id=self.plan.pk)
        self.assertEqual(closed.status, SxOverallPlan.STATUS_DONE)
        with self.assertRaises(PlanningError):
            cancel_plan(model=SxOverallPlan, plan_id=self.plan.pk)

    def test_cancel_records_reason(self):
        cancelled = cancel_plan(
            model=SxOverallPlan, plan_id=self.plan.pk, reason='Khách dừng đơn',
        )
        self.assertEqual(cancelled.status, SxOverallPlan.STATUS_CANCELLED)
        self.assertIn('Khách dừng đơn', cancelled.notes)

    def test_cannot_cancel_twice(self):
        cancel_plan(model=SxOverallPlan, plan_id=self.plan.pk)
        with self.assertRaises(PlanningError):
            cancel_plan(model=SxOverallPlan, plan_id=self.plan.pk)

    def test_detail_plan_progress_without_mo(self):
        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        progress = detail_plan_progress(detail)
        self.assertEqual(progress['plan_qty'], Decimal('300.00'))
        self.assertEqual(progress['mo_total'], 0)
        self.assertFalse(progress['all_mo_done'])


class MaterialPlanReservationTests(TestCase):
    def test_reserved_zero_when_no_stock(self):
        from kho_npl.models import Material, MaterialCategory, Unit

        cat = MaterialCategory.objects.create(code='C1', name='Vải')
        unit = Unit.objects.create(code='M', name='Mét')
        Material.objects.create(code='VAI-X', name='Vải X', category=cat, unit=unit)

        plan = SxMaterialPlan.objects.create(
            code='KHNVL-TEST-1', name='Test', status=SxOverallPlan.STATUS_DRAFT,
        )
        plan.lines.create(
            material_code='VAI-X', material_name='Vải X', qty_required=Decimal('100'),
        )

        from kho_npl.services.reservation import upsert_reservations_for_khnvl

        created = upsert_reservations_for_khnvl(plan=plan)
        self.assertEqual(created, [], 'Không có tồn thì không giữ chỗ được')
        self.assertEqual(plan.lines.first().qty_reserved, Decimal('0'))

    def test_release_clears_reserved(self):
        from kho_npl.services.reservation import release_reservations_for_khnvl

        plan = SxMaterialPlan.objects.create(
            code='KHNVL-TEST-2', name='Test 2', status=SxOverallPlan.STATUS_CONFIRMED,
        )
        plan.lines.create(
            material_code='VAI-Y', qty_required=Decimal('50'), qty_reserved=Decimal('20'),
        )
        release_reservations_for_khnvl(plan=plan)
        self.assertEqual(plan.lines.first().qty_reserved, Decimal('0'))
