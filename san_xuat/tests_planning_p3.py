"""Test P3 — xếp lịch theo SMV và năng lực từng tổ.

Phủ: quỹ phút của tổ, đọc định mức từ BOM/routing, xếp lịch finite capacity,
cảnh báo quá tải theo tổ, ma trận tải tổ × ngày.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from san_xuat.hub_models import (
    SxDetailPlan,
    SxOverallPlan,
    SxProductionOrder,
    SxWorkCenter,
)
from san_xuat.models import BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.planning import (
    PlanningError,
    add_overall_plan_line,
    confirm_overall_plan,
    create_overall_plan,
)
from san_xuat.services.scheduling import (
    build_load_matrix,
    center_minute_budget,
    check_detail_plan_center_capacity,
    product_routing,
    schedule_detail_plan_by_capacity,
)


def _center(code, name, heads, *, minutes=480, eff='100', capacity='0'):
    return SxWorkCenter.objects.create(
        code=code,
        name=name,
        team_label=name,
        headcount=heads,
        shift_minutes_per_head=minutes,
        efficiency_pct=Decimal(eff),
        capacity_per_day=Decimal(capacity),
    )


def _product_with_routing(code, steps):
    """steps = [(process_name, work_center, minutes_per_unit)]"""
    doc = ProductTechDoc.objects.create(
        product_code=code, product_name=f'SP {code}', is_active=True,
    )
    bom = BomVersion.objects.create(
        tech_doc=doc, version_label='v1', status=BomVersion.STATUS_ACTIVE,
    )
    for i, (name, wc, minutes) in enumerate(steps, start=1):
        smv = Decimal(str(minutes))
        ProcessStep.objects.create(
            bom=bom,
            sequence=i * 10,
            process_name=name,
            work_center=wc,
            norm_per_hour=(Decimal('60') / smv) if smv > 0 else Decimal('1'),
            std_time_minutes=smv,
        )
    return doc, bom


class WorkCenterMinuteTests(TestCase):
    def test_available_minutes_formula(self):
        wc = _center('T-A', 'Tổ A', 10, minutes=480, eff='85')
        # 10 × 480 × 0.85 = 4080
        self.assertEqual(wc.available_minutes_per_day, Decimal('4080.00'))
        self.assertTrue(wc.has_minute_capacity)

    def test_zero_headcount_no_capacity(self):
        wc = _center('T-Z', 'Tổ trống', 0)
        self.assertEqual(wc.available_minutes_per_day, Decimal('0.00'))
        self.assertFalse(wc.has_minute_capacity)

    def test_budget_skips_inactive_and_zero(self):
        _center('T-1', 'Tổ 1', 5)
        _center('T-2', 'Tổ 2', 0)
        off = _center('T-3', 'Tổ tắt', 5)
        off.is_active = False
        off.save(update_fields=['is_active'])
        budget = center_minute_budget()
        self.assertEqual(len(budget), 1)

    def test_hrm_sync_writes_headcount(self):
        from hrm.models import Department, Division, Profile
        from django.contrib.auth.models import User
        from san_xuat.services.capacity_from_hrm import sync_capacity_from_hrm

        dept, _ = Department.objects.get_or_create(
            name='SẢN XUẤT', defaults={'is_active': True},
        )
        div, _ = Division.objects.get_or_create(
            department=dept, name='MAY P3', defaults={'is_active': True},
        )
        for i in range(3):
            u = User.objects.create_user(f'sxw{i}', f'sxw{i}@t.local', 'x')
            p, _ = Profile.objects.get_or_create(user=u)
            p.division = div
            p.department = dept
            p.is_employed = True
            p.save()

        sync_capacity_from_hrm()
        wc = SxWorkCenter.objects.filter(code=f'HRD-{div.pk}').first()
        self.assertIsNotNone(wc)
        self.assertEqual(wc.headcount, 3)
        self.assertGreater(wc.available_minutes_per_day, Decimal('0'))


class ProductRoutingTests(TestCase):
    def setUp(self):
        self.cut = _center('T-CUT', 'Cắt', 4)
        self.sew = _center('T-SEW', 'May', 10)

    def test_reads_smv_from_bom(self):
        _product_with_routing('SP-R1', [('Cắt', self.cut, '2'), ('May', self.sew, '8')])
        routing = product_routing('SP-R1')
        self.assertEqual(routing.source, 'bom')
        self.assertTrue(routing.has_time_data)
        self.assertEqual(routing.total_smv, Decimal('10.0000'))
        self.assertEqual(len(routing.steps), 2)

    def test_minutes_by_center_merges_same_center(self):
        _product_with_routing('SP-R2', [
            ('Cắt', self.cut, '2'),
            ('May 1', self.sew, '5'),
            ('May 2', self.sew, '3'),
        ])
        by_center = product_routing('SP-R2').minutes_by_center()
        self.assertEqual(by_center[self.sew.pk], Decimal('8'))
        self.assertEqual(by_center[self.cut.pk], Decimal('2'))

    def test_no_tech_doc_returns_empty(self):
        routing = product_routing('SP-KHONG-CO')
        self.assertFalse(routing.has_time_data)
        self.assertEqual(routing.steps, [])

    def test_zero_minutes_steps_ignored(self):
        _product_with_routing('SP-R3', [('Cắt', self.cut, '0')])
        self.assertFalse(product_routing('SP-R3').has_time_data)


class ScheduleByCapacityTests(TestCase):
    def setUp(self):
        # Cắt: 1 người × 480 phút = 480 phút/ngày
        # May: 2 người × 480 phút = 960 phút/ngày
        self.cut = _center('T-CUT', 'Cắt', 1)
        self.sew = _center('T-SEW', 'May', 2)
        # SP cần 2 phút Cắt + 8 phút May cho một cái
        #   Cắt cho phép 480/2 = 240 cái/ngày
        #   May cho phép 960/8 = 120 cái/ngày  ← chặn
        _product_with_routing('SP-S', [('Cắt', self.cut, '2'), ('May', self.sew, '8')])

        self.plan = create_overall_plan(
            name='KH xếp lịch',
            date_from=date(2026, 8, 3),   # Thứ 2
            date_to=date(2026, 8, 7),     # Thứ 6 → 5 ngày làm việc
        )
        add_overall_plan_line(
            plan_id=self.plan.pk, product_code='SP-S', qty_planned=Decimal('300'),
        )
        confirm_overall_plan(plan_id=self.plan.pk)

    def test_daily_qty_capped_by_bottleneck_center(self):
        res = schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)
        by_day = {}
        for ln in res.detail_plan.lines.all():
            by_day[ln.plan_date] = by_day.get(ln.plan_date, Decimal('0')) + ln.qty
        # Ngày đầu phải đúng 120 (giới hạn tổ May), không phải 300/5=60
        self.assertEqual(by_day[date(2026, 8, 3)], Decimal('120.00'))
        self.assertEqual(by_day[date(2026, 8, 4)], Decimal('120.00'))
        self.assertEqual(by_day[date(2026, 8, 5)], Decimal('60.00'))
        self.assertEqual(res.scheduled_qty, Decimal('300.00'))
        self.assertTrue(res.is_complete)

    def test_assigns_bottleneck_center_to_line(self):
        res = schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)
        line = res.detail_plan.lines.first()
        self.assertEqual(line.work_center_id, self.sew.pk, 'Tổ chật nhất là May')
        self.assertEqual(line.team_label, 'May')

    def test_only_uses_working_days(self):
        res = schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)
        self.assertEqual(res.days_used, 3)
        dates = {ln.plan_date for ln in res.detail_plan.lines.all()}
        self.assertTrue(all(d.weekday() < 6 for d in dates))

    def test_over_capacity_reports_unscheduled(self):
        big = create_overall_plan(
            name='KH quá tải', date_from=date(2026, 8, 3), date_to=date(2026, 8, 4),
        )
        add_overall_plan_line(
            plan_id=big.pk, product_code='SP-S', qty_planned=Decimal('1000'),
        )
        confirm_overall_plan(plan_id=big.pk)
        res = schedule_detail_plan_by_capacity(overall_plan_id=big.pk)
        # 2 ngày × 120 = 240 xếp được, còn 760
        self.assertEqual(res.scheduled_qty, Decimal('240.00'))
        self.assertFalse(res.is_complete)
        self.assertEqual(res.unscheduled[0]['qty_left'], Decimal('760.00'))
        res.detail_plan.refresh_from_db()
        self.assertIn('Vượt năng lực', res.detail_plan.notes)

    def test_product_without_routing_falls_back_to_even_split(self):
        plan = create_overall_plan(
            name='KH không định mức',
            date_from=date(2026, 8, 3), date_to=date(2026, 8, 7),
        )
        add_overall_plan_line(
            plan_id=plan.pk, product_code='SP-NO-IE', qty_planned=Decimal('100'),
        )
        confirm_overall_plan(plan_id=plan.pk)
        res = schedule_detail_plan_by_capacity(overall_plan_id=plan.pk)
        self.assertIn('SP-NO-IE', res.no_routing)
        total = sum((ln.qty for ln in res.detail_plan.lines.all()), Decimal('0'))
        self.assertEqual(total, Decimal('100.00'))
        res.detail_plan.refresh_from_db()
        self.assertIn('Chưa có định mức', res.detail_plan.notes)

    def test_requires_confirmed_plan(self):
        draft = create_overall_plan(
            name='Nháp', date_from=date(2026, 8, 3), date_to=date(2026, 8, 5),
        )
        add_overall_plan_line(plan_id=draft.pk, product_code='SP-S', qty_planned=Decimal('10'))
        with self.assertRaises(PlanningError):
            schedule_detail_plan_by_capacity(overall_plan_id=draft.pk)

    def test_no_minute_budget_raises(self):
        SxWorkCenter.objects.update(headcount=0)
        with self.assertRaises(PlanningError):
            schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)

    def test_reschedule_reuses_draft_plan(self):
        first = schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)
        second = schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)
        self.assertEqual(first.detail_plan.pk, second.detail_plan.pk)
        self.assertEqual(SxDetailPlan.objects.filter(overall_plan=self.plan).count(), 1)

    def test_two_products_share_center_budget(self):
        # SP-S2 dùng cùng tổ May, 8 phút/cái → 2 mã chia nhau 960 phút
        _product_with_routing('SP-S2', [('May', self.sew, '8')])
        plan = create_overall_plan(
            name='KH 2 mã', date_from=date(2026, 8, 3), date_to=date(2026, 8, 3),
        )
        add_overall_plan_line(plan_id=plan.pk, product_code='SP-S', qty_planned=Decimal('500'))
        add_overall_plan_line(plan_id=plan.pk, product_code='SP-S2', qty_planned=Decimal('500'))
        confirm_overall_plan(plan_id=plan.pk)
        res = schedule_detail_plan_by_capacity(overall_plan_id=plan.pk)
        # Tổng phút May dùng không vượt 960 → tổng SL ≤ 120
        total = sum((ln.qty for ln in res.detail_plan.lines.all()), Decimal('0'))
        self.assertLessEqual(total, Decimal('120.00'))
        self.assertGreater(total, Decimal('0'))


class CenterCapacityWarningTests(TestCase):
    def setUp(self):
        self.sew = _center('T-SEW', 'May', 1)  # 480 phút/ngày
        _product_with_routing('SP-W', [('May', self.sew, '10')])  # 48 cái/ngày
        self.plan = create_overall_plan(
            name='KH cảnh báo', date_from=date(2026, 8, 3), date_to=date(2026, 8, 3),
        )
        add_overall_plan_line(plan_id=self.plan.pk, product_code='SP-W', qty_planned=Decimal('100'))
        confirm_overall_plan(plan_id=self.plan.pk)

    def test_warns_when_center_overloaded(self):
        from san_xuat.services.planning import explode_detail_plan_from_overall

        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        warns = check_detail_plan_center_capacity(plan_id=detail.pk)
        self.assertEqual(len(warns), 1)
        w = warns[0]
        self.assertEqual(w.center.pk, self.sew.pk)
        self.assertEqual(w.minutes_needed, Decimal('1000.00'))
        self.assertEqual(w.minutes_available, Decimal('480.00'))
        self.assertEqual(w.over_by, Decimal('520.00'))

    def test_no_warning_when_within_capacity(self):
        from san_xuat.services.planning import explode_detail_plan_from_overall

        small = create_overall_plan(
            name='KH nhỏ', date_from=date(2026, 8, 3), date_to=date(2026, 8, 3),
        )
        add_overall_plan_line(plan_id=small.pk, product_code='SP-W', qty_planned=Decimal('40'))
        confirm_overall_plan(plan_id=small.pk)
        detail = explode_detail_plan_from_overall(overall_plan_id=small.pk)
        self.assertEqual(check_detail_plan_center_capacity(plan_id=detail.pk), [])

    def test_scheduled_plan_has_no_warning(self):
        res = schedule_detail_plan_by_capacity(overall_plan_id=self.plan.pk)
        self.assertEqual(
            check_detail_plan_center_capacity(plan_id=res.detail_plan.pk), [],
            'Lịch xếp theo năng lực thì không được quá tải',
        )


class LoadMatrixTests(TestCase):
    def setUp(self):
        self.sew = _center('T-SEW', 'May', 1)  # 480 phút/ngày
        _product_with_routing('SP-L', [('May', self.sew, '10')])

    def test_matrix_counts_confirmed_plan_only(self):
        from san_xuat.services.planning import (
            confirm_detail_plan,
            explode_detail_plan_from_overall,
        )

        plan = create_overall_plan(
            name='KH matrix', date_from=date(2026, 8, 3), date_to=date(2026, 8, 3),
        )
        add_overall_plan_line(plan_id=plan.pk, product_code='SP-L', qty_planned=Decimal('24'))
        confirm_overall_plan(plan_id=plan.pk)
        detail = explode_detail_plan_from_overall(overall_plan_id=plan.pk)

        # Chưa xác nhận KHCT → chưa tính vào tải
        m1 = build_load_matrix(date_from=date(2026, 8, 3), date_to=date(2026, 8, 3), include_mo=False)
        self.assertEqual(m1['rows'][0]['minutes_needed'], Decimal('0.00'))

        confirm_detail_plan(plan_id=detail.pk, allow_over_capacity=True)
        m2 = build_load_matrix(date_from=date(2026, 8, 3), date_to=date(2026, 8, 3), include_mo=False)
        self.assertEqual(m2['rows'][0]['minutes_needed'], Decimal('240.00'))
        self.assertEqual(m2['rows'][0]['load_pct'], Decimal('50.00'))

    def test_matrix_counts_open_mo(self):
        SxProductionOrder.objects.create(
            code='LSX-LM', product_code='SP-L', qty=Decimal('60'), qty_done=Decimal('12'),
            order_date=date(2026, 8, 3), planned_start=date(2026, 8, 3),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        m = build_load_matrix(
            date_from=date(2026, 8, 3), date_to=date(2026, 8, 3), include_plan=False,
        )
        # Còn 48 cái × 10 phút = 480 phút → đúng 100%
        self.assertEqual(m['rows'][0]['minutes_needed'], Decimal('480.00'))
        self.assertEqual(m['rows'][0]['cells'][0]['load'].load_pct, Decimal('100.00'))
        self.assertFalse(m['rows'][0]['cells'][0]['load'].is_over)

    def test_done_mo_not_counted(self):
        SxProductionOrder.objects.create(
            code='LSX-DONE', product_code='SP-L', qty=Decimal('60'), qty_done=Decimal('60'),
            order_date=date(2026, 8, 3), planned_start=date(2026, 8, 3),
            status=SxProductionOrder.STATUS_DONE,
        )
        m = build_load_matrix(
            date_from=date(2026, 8, 3), date_to=date(2026, 8, 3), include_plan=False,
        )
        self.assertEqual(m['rows'][0]['minutes_needed'], Decimal('0.00'))

    def test_over_flag_and_sunday_excluded(self):
        SxProductionOrder.objects.create(
            code='LSX-OVER', product_code='SP-L', qty=Decimal('100'), qty_done=Decimal('0'),
            order_date=date(2026, 8, 3), planned_start=date(2026, 8, 3),
            status=SxProductionOrder.STATUS_RELEASED,
        )
        m = build_load_matrix(
            date_from=date(2026, 8, 3), date_to=date(2026, 8, 9), include_plan=False,
        )
        self.assertEqual(len(m['days']), 6, 'Chủ nhật bị loại')
        self.assertTrue(m['rows'][0]['cells'][0]['load'].is_over)
        self.assertEqual(m['rows'][0]['over_days'], 1)

    def test_center_without_minutes_excluded(self):
        _center('T-NOHEAD', 'Tổ chưa khai', 0)
        m = build_load_matrix(date_from=date(2026, 8, 3), date_to=date(2026, 8, 3))
        codes = {r['center'].code for r in m['rows']}
        self.assertNotIn('T-NOHEAD', codes)


class P3PageRenderTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        from hrm.models import Profile
        from hrm.permissions import ROLE_DIRECTOR

        self.user = User.objects.create_user('p3admin', 'p3@test.local', 'x')
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.role = ROLE_DIRECTOR
        profile.save()
        self.user.refresh_from_db()
        self.client.force_login(self.user)

        self.sew = _center('T-SEW', 'May', 2)
        _product_with_routing('SP-UI3', [('May', self.sew, '8')])
        self.plan = create_overall_plan(
            name='KH P3 UI', date_from=date(2026, 8, 3), date_to=date(2026, 8, 7),
        )
        add_overall_plan_line(
            plan_id=self.plan.pk, product_code='SP-UI3', qty_planned=Decimal('200'),
        )
        confirm_overall_plan(plan_id=self.plan.pk)

    def test_load_matrix_page(self):
        from django.urls import reverse

        resp = self.client.get(
            reverse('san_xuat:capacity_load_matrix'), {'from': '2026-08-03', 'to': '2026-08-07'},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8', 'ignore')
        self.assertIn('Tải năng lực theo tổ', body)
        self.assertIn('May', body)
        self.assertNotIn('Traceback', body)

    def test_reschedule_via_post(self):
        from django.urls import reverse
        from san_xuat.services.planning import explode_detail_plan_from_overall

        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        url = reverse('san_xuat:plan_detail_detail', args=[detail.pk])
        resp = self.client.post(url, {'action': 'reschedule'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        detail.refresh_from_db()
        # 2 người × 480 = 960 phút / 8 = 120 cái/ngày
        by_day = {}
        for ln in detail.lines.all():
            by_day[ln.plan_date] = by_day.get(ln.plan_date, Decimal('0')) + ln.qty
        self.assertEqual(by_day[date(2026, 8, 3)], Decimal('120.00'))
        self.assertTrue(all((ln.team_label or '') == 'May' for ln in detail.lines.all()))

    def test_detail_page_shows_smv_badge_and_button(self):
        from django.urls import reverse
        from san_xuat.services.planning import explode_detail_plan_from_overall

        detail = explode_detail_plan_from_overall(overall_plan_id=self.plan.pk)
        body = self.client.get(
            reverse('san_xuat:plan_detail_detail', args=[detail.pk])
        ).content.decode('utf-8', 'ignore')
        self.assertIn('Xếp lịch theo định mức', body)
        self.assertIn('phút/cái', body)

    def test_capacity_create_accepts_minute_fields(self):
        from django.urls import reverse

        resp = self.client.post(reverse('san_xuat:capacity_create'), {
            'code': 'T-NEW',
            'name': 'Tổ mới',
            'capacity_per_day': '100',
            'uom_label': 'SP',
            'headcount': '6',
            'shift_minutes_per_head': '480',
            'efficiency_pct': '90',
            'is_active': 'on',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        wc = SxWorkCenter.objects.filter(code='T-NEW').first()
        self.assertIsNotNone(wc)
        self.assertEqual(wc.headcount, 6)
        # 6 × 480 × 0.90 = 2592
        self.assertEqual(wc.available_minutes_per_day, Decimal('2592.00'))
