"""Test P2 — ba phương án lập kế hoạch sản xuất: MTO, MTS, MPS.

Phủ: netting (trừ tồn TP + hàng đang SX), gom nhiều đơn KV, đề xuất bù tồn
theo chính sách min/max, lịch trình chủ theo tuần/tháng + vùng đóng băng.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from san_xuat.hub_models import (
    SxOverallPlan,
    SxProductionOrder,
    SxProductStockPolicy,
)
from san_xuat.services.demand import (
    DemandItem,
    apply_netting,
    build_restock_suggestions,
    merge_by_product,
    wip_qty_map,
)
from san_xuat.services.plan_methods import (
    bucket_start_for,
    is_bucket_frozen,
    load_mps_demand,
    load_mts_demand,
    mps_buckets,
    recompute_plan_netting,
    upsert_stock_policy,
)
from san_xuat.services.planning import PlanningError, create_overall_plan


def _plan(method, **kwargs):
    today = kwargs.pop('date_from', date(2026, 8, 3))
    end = kwargs.pop('date_to', date(2026, 8, 30))
    return create_overall_plan(
        name=kwargs.pop('name', f'KH {method}'),
        date_from=today,
        date_to=end,
        plan_method=method,
        **kwargs,
    )


class PlanMethodCreateTests(TestCase):
    def test_default_method_is_mto(self):
        plan = create_overall_plan(
            name='KH mặc định', date_from=date(2026, 8, 3), date_to=date(2026, 8, 5),
        )
        self.assertEqual(plan.plan_method, SxOverallPlan.METHOD_MTO)
        # MTO luôn gắn nguồn đơn bán
        self.assertEqual(plan.source, SxOverallPlan.SOURCE_SALES_ORDER)

    def test_mts_uses_forecast_source(self):
        plan = _plan(SxOverallPlan.METHOD_MTS)
        self.assertEqual(plan.source, SxOverallPlan.SOURCE_FORECAST)

    def test_invalid_method_raises(self):
        with self.assertRaises(PlanningError):
            _plan('xyz')

    def test_frozen_until_only_for_mps(self):
        mts = _plan(SxOverallPlan.METHOD_MTS, frozen_until=date(2026, 8, 10))
        self.assertIsNone(mts.frozen_until)
        mps = _plan(SxOverallPlan.METHOD_MPS, frozen_until=date(2026, 8, 10))
        self.assertEqual(mps.frozen_until, date(2026, 8, 10))

    def test_frozen_until_beyond_period_raises(self):
        with self.assertRaises(PlanningError):
            _plan(SxOverallPlan.METHOD_MPS, frozen_until=date(2026, 12, 31))

    def test_wrong_method_blocks_loader(self):
        plan = _plan(SxOverallPlan.METHOD_MTO)
        with self.assertRaises(PlanningError):
            load_mts_demand(plan_id=plan.pk)


class NettingTests(TestCase):
    """Netting không phụ thuộc KiotViet — tồn TP = 0 trong môi trường test."""

    def setUp(self):
        # Một LSX đang chạy: còn phải làm 40
        SxProductionOrder.objects.create(
            code='LSX-NET-1',
            product_code='SP-NET',
            qty=Decimal('100'),
            qty_done=Decimal('60'),
            order_date=date(2026, 8, 1),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        # LSX đã xong không tính vào WIP
        SxProductionOrder.objects.create(
            code='LSX-NET-2',
            product_code='SP-NET',
            qty=Decimal('50'),
            qty_done=Decimal('50'),
            order_date=date(2026, 8, 1),
            status=SxProductionOrder.STATUS_DONE,
        )

    def test_wip_counts_only_open_orders(self):
        wip = wip_qty_map(['SP-NET'])
        self.assertEqual(wip.get('SP-NET'), Decimal('40.00'))

    def test_netting_subtracts_wip(self):
        items = [DemandItem(product_code='SP-NET', qty_gross=Decimal('100'))]
        apply_netting(items)
        self.assertEqual(items[0].qty_wip, Decimal('40.00'))
        self.assertEqual(items[0].qty_net, Decimal('60.00'))

    def test_wip_covers_demand_fully(self):
        items = [DemandItem(product_code='SP-NET', qty_gross=Decimal('30'))]
        apply_netting(items)
        self.assertEqual(items[0].qty_net, Decimal('0.00'))
        self.assertTrue(items[0].is_covered)

    def test_wip_allocated_once_across_lines(self):
        items = [
            DemandItem(product_code='SP-NET', qty_gross=Decimal('25'), due_date=date(2026, 8, 5)),
            DemandItem(product_code='SP-NET', qty_gross=Decimal('25'), due_date=date(2026, 8, 9)),
            DemandItem(product_code='SP-NET', qty_gross=Decimal('25'), due_date=date(2026, 8, 20)),
        ]
        apply_netting(items)
        total_wip = sum(i.qty_wip for i in items)
        self.assertEqual(total_wip, Decimal('40.00'), 'WIP chỉ được trừ một lần')
        # Đơn gấp được ưu tiên phủ trước
        self.assertEqual(items[0].qty_net, Decimal('0.00'))
        self.assertEqual(items[2].qty_net, Decimal('25.00'))

    def test_netting_disabled_keeps_gross(self):
        items = [DemandItem(product_code='SP-NET', qty_gross=Decimal('100'))]
        apply_netting(items, enabled=False)
        self.assertEqual(items[0].qty_net, Decimal('100.00'))
        self.assertEqual(items[0].qty_wip, Decimal('0'))

    def test_merge_by_product_sums_and_keeps_earliest_due(self):
        items = [
            DemandItem(product_code='SP-A', qty_gross=Decimal('10'), due_date=date(2026, 8, 20), kv_order_code='DH1'),
            DemandItem(product_code='sp-a', qty_gross=Decimal('5'), due_date=date(2026, 8, 10), kv_order_code='DH2'),
            DemandItem(product_code='SP-B', qty_gross=Decimal('7')),
        ]
        merged = merge_by_product(items)
        self.assertEqual(len(merged), 2)
        by_code = {m.product_code.upper(): m for m in merged}
        self.assertEqual(by_code['SP-A'].qty_gross, Decimal('15.00'))
        self.assertEqual(by_code['SP-A'].due_date, date(2026, 8, 10))
        self.assertIn('DH1', by_code['SP-A'].kv_order_code)
        self.assertIn('DH2', by_code['SP-A'].kv_order_code)


class StockPolicyTests(TestCase):
    def test_upsert_creates_then_updates(self):
        p1 = upsert_stock_policy(product_code='SP-P', min_stock=Decimal('100'))
        self.assertEqual(p1.min_stock, Decimal('100.00'))
        p2 = upsert_stock_policy(
            product_code='SP-P', min_stock=Decimal('150'), max_stock=Decimal('300'),
        )
        self.assertEqual(p1.pk, p2.pk, 'Cùng mã thì cập nhật, không tạo mới')
        self.assertEqual(p2.max_stock, Decimal('300.00'))
        self.assertEqual(SxProductStockPolicy.objects.count(), 1)

    def test_target_falls_back_to_min(self):
        policy = upsert_stock_policy(product_code='SP-Q', min_stock=Decimal('80'))
        self.assertEqual(policy.target_stock, Decimal('80.00'))

    def test_max_below_min_raises(self):
        with self.assertRaises(PlanningError):
            upsert_stock_policy(
                product_code='SP-R', min_stock=Decimal('100'), max_stock=Decimal('50'),
            )

    def test_missing_code_raises(self):
        with self.assertRaises(PlanningError):
            upsert_stock_policy(product_code='  ', min_stock=Decimal('10'))


class RestockSuggestionTests(TestCase):
    def setUp(self):
        upsort = upsert_stock_policy
        upsort(product_code='SP-LOW', min_stock=Decimal('100'), max_stock=Decimal('250'))
        upsort(product_code='SP-OK', min_stock=Decimal('50'))
        upsort(product_code='SP-OFF', min_stock=Decimal('999'), is_active=False)
        # SP-OK đã có 60 đang SX → đủ so với min 50
        SxProductionOrder.objects.create(
            code='LSX-OK', product_code='SP-OK', qty=Decimal('60'), qty_done=Decimal('0'),
            order_date=date(2026, 8, 1), status=SxProductionOrder.STATUS_RELEASED,
        )

    def test_only_short_items_suggested(self):
        rows = build_restock_suggestions()
        codes = {r.policy.product_code for r in rows}
        self.assertIn('SP-LOW', codes)
        self.assertNotIn('SP-OK', codes, 'Đã đủ nhờ hàng đang SX')
        self.assertNotIn('SP-OFF', codes, 'Chính sách đang tắt')

    def test_suggest_tops_up_to_target(self):
        rows = {r.policy.product_code: r for r in build_restock_suggestions()}
        # tồn 0 + WIP 0 → bù lên tồn mục tiêu 250
        self.assertEqual(rows['SP-LOW'].qty_suggest, Decimal('250.00'))

    def test_include_covered_shows_all_active(self):
        rows = build_restock_suggestions(include_covered=True)
        codes = {r.policy.product_code for r in rows}
        self.assertEqual(codes, {'SP-LOW', 'SP-OK'})


class MtsLoadTests(TestCase):
    def setUp(self):
        upsert_stock_policy(
            product_code='SP-M1', min_stock=Decimal('100'), max_stock=Decimal('200'),
            lead_time_days=5,
        )
        upsert_stock_policy(product_code='SP-M2', min_stock=Decimal('80'))
        self.plan = _plan(SxOverallPlan.METHOD_MTS)

    def test_load_writes_lines_with_due_date(self):
        res = load_mts_demand(plan_id=self.plan.pk)
        self.assertEqual(res['written'], 2)
        lines = {ln.product_code: ln for ln in self.plan.lines.all()}
        self.assertEqual(lines['SP-M1'].qty_planned, Decimal('200.00'))
        self.assertEqual(lines['SP-M2'].qty_planned, Decimal('80.00'))
        self.assertIsNotNone(lines['SP-M1'].due_date, 'Có lead time thì có hạn cần hàng')
        self.assertIsNone(lines['SP-M2'].due_date)

    def test_load_can_filter_codes(self):
        load_mts_demand(plan_id=self.plan.pk, product_codes=['SP-M2'])
        codes = [ln.product_code for ln in self.plan.lines.all()]
        self.assertEqual(codes, ['SP-M2'])

    def test_replace_clears_previous(self):
        load_mts_demand(plan_id=self.plan.pk)
        load_mts_demand(plan_id=self.plan.pk, product_codes=['SP-M1'], replace=True)
        self.assertEqual(self.plan.lines.count(), 1)

    def test_no_policy_raises(self):
        SxProductStockPolicy.objects.all().delete()
        with self.assertRaises(PlanningError):
            load_mts_demand(plan_id=self.plan.pk)

    def test_confirmed_plan_cannot_load(self):
        from san_xuat.services.planning import confirm_overall_plan

        load_mts_demand(plan_id=self.plan.pk)
        confirm_overall_plan(plan_id=self.plan.pk)
        with self.assertRaises(PlanningError):
            load_mts_demand(plan_id=self.plan.pk)


class MpsBucketTests(TestCase):
    def test_bucket_start_week_is_monday(self):
        # 05/08/2026 là Thứ 4 → về Thứ 2 03/08
        self.assertEqual(
            bucket_start_for(date(2026, 8, 5), SxOverallPlan.BUCKET_WEEK), date(2026, 8, 3),
        )

    def test_bucket_start_month_is_first_day(self):
        self.assertEqual(
            bucket_start_for(date(2026, 8, 20), SxOverallPlan.BUCKET_MONTH), date(2026, 8, 1),
        )

    def test_bucket_start_day_unchanged(self):
        self.assertEqual(
            bucket_start_for(date(2026, 8, 20), SxOverallPlan.BUCKET_DAY), date(2026, 8, 20),
        )

    def test_weekly_buckets_count(self):
        plan = _plan(
            SxOverallPlan.METHOD_MPS,
            date_from=date(2026, 8, 3),
            date_to=date(2026, 8, 30),
            mps_bucket=SxOverallPlan.BUCKET_WEEK,
        )
        buckets = mps_buckets(plan)
        self.assertEqual(len(buckets), 4)
        self.assertEqual(buckets[0]['start'], date(2026, 8, 3))

    def test_monthly_buckets_span_two_months(self):
        plan = _plan(
            SxOverallPlan.METHOD_MPS,
            date_from=date(2026, 8, 15),
            date_to=date(2026, 9, 20),
            mps_bucket=SxOverallPlan.BUCKET_MONTH,
        )
        buckets = mps_buckets(plan)
        self.assertEqual([b['start'] for b in buckets], [date(2026, 8, 1), date(2026, 9, 1)])

    def test_frozen_flag(self):
        plan = _plan(
            SxOverallPlan.METHOD_MPS,
            date_from=date(2026, 8, 3),
            date_to=date(2026, 8, 30),
            frozen_until=date(2026, 8, 9),
        )
        buckets = mps_buckets(plan)
        self.assertTrue(buckets[0]['is_frozen'], 'Tuần đầu nằm trong vùng đóng băng')
        self.assertFalse(buckets[1]['is_frozen'])
        self.assertTrue(is_bucket_frozen(plan, date(2026, 8, 3)))
        self.assertFalse(is_bucket_frozen(plan, date(2026, 8, 17)))


class MpsLoadTests(TestCase):
    def setUp(self):
        self.plan = _plan(
            SxOverallPlan.METHOD_MPS,
            date_from=date(2026, 8, 3),
            date_to=date(2026, 8, 30),
            mps_bucket=SxOverallPlan.BUCKET_WEEK,
            apply_netting=False,
        )

    def test_writes_line_snapped_to_bucket(self):
        res = load_mps_demand(plan_id=self.plan.pk, rows=[
            {'product_code': 'SP-S1', 'qty': Decimal('120'), 'bucket_start': date(2026, 8, 5)},
        ])
        self.assertEqual(res['written'], 1)
        line = self.plan.lines.first()
        self.assertEqual(line.bucket_start, date(2026, 8, 3), 'Quy về đầu tuần')
        self.assertEqual(line.qty_planned, Decimal('120.00'))

    def test_same_product_same_bucket_overwrites(self):
        load_mps_demand(plan_id=self.plan.pk, rows=[
            {'product_code': 'SP-S1', 'qty': Decimal('100'), 'bucket_start': date(2026, 8, 3)},
        ])
        load_mps_demand(plan_id=self.plan.pk, rows=[
            {'product_code': 'SP-S1', 'qty': Decimal('180'), 'bucket_start': date(2026, 8, 4)},
        ])
        self.assertEqual(self.plan.lines.count(), 1)
        self.assertEqual(self.plan.lines.first().qty_planned, Decimal('180.00'))

    def test_different_buckets_are_separate_lines(self):
        load_mps_demand(plan_id=self.plan.pk, rows=[
            {'product_code': 'SP-S1', 'qty': Decimal('100'), 'bucket_start': date(2026, 8, 3)},
            {'product_code': 'SP-S1', 'qty': Decimal('90'), 'bucket_start': date(2026, 8, 10)},
        ])
        self.assertEqual(self.plan.lines.count(), 2)

    def test_frozen_bucket_is_skipped(self):
        self.plan.frozen_until = date(2026, 8, 9)
        self.plan.save(update_fields=['frozen_until'])
        res = load_mps_demand(plan_id=self.plan.pk, rows=[
            {'product_code': 'SP-S1', 'qty': Decimal('100'), 'bucket_start': date(2026, 8, 3)},
            {'product_code': 'SP-S1', 'qty': Decimal('50'), 'bucket_start': date(2026, 8, 17)},
        ])
        self.assertEqual(res['frozen_skipped'], 1)
        self.assertEqual(res['written'], 1)
        self.assertEqual(self.plan.lines.first().bucket_start, date(2026, 8, 17))

    def test_zero_or_blank_rows_ignored(self):
        res = load_mps_demand(plan_id=self.plan.pk, rows=[
            {'product_code': '', 'qty': Decimal('10'), 'bucket_start': date(2026, 8, 3)},
            {'product_code': 'SP-S2', 'qty': Decimal('0'), 'bucket_start': date(2026, 8, 3)},
        ])
        self.assertEqual(res['written'], 0)


class RecomputeNettingTests(TestCase):
    def setUp(self):
        SxProductionOrder.objects.create(
            code='LSX-RC', product_code='SP-RC', qty=Decimal('70'), qty_done=Decimal('20'),
            order_date=date(2026, 8, 1), status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        self.plan = _plan(SxOverallPlan.METHOD_MTS, apply_netting=True)
        upsert_stock_policy(product_code='SP-RC', min_stock=Decimal('200'))

    def test_recompute_updates_wip_and_net(self):
        load_mts_demand(plan_id=self.plan.pk)
        line = self.plan.lines.get(product_code='SP-RC')
        # Đề xuất bù đã trừ WIP 50 khỏi min 200
        self.assertEqual(line.qty_planned, Decimal('150.00'))

        # Tính lại: nhu cầu gộp 150 tiếp tục bị trừ WIP 50 → 100
        res = recompute_plan_netting(plan_id=self.plan.pk)
        self.assertEqual(res['updated'], 1)
        line.refresh_from_db()
        self.assertEqual(line.qty_wip, Decimal('50.00'))
        self.assertEqual(line.qty_planned, Decimal('100.00'))

    def test_recompute_blocked_when_cancelled(self):
        from san_xuat.services.planning import cancel_plan

        load_mts_demand(plan_id=self.plan.pk)
        cancel_plan(model=SxOverallPlan, plan_id=self.plan.pk)
        with self.assertRaises(PlanningError):
            recompute_plan_netting(plan_id=self.plan.pk)


class P2PageRenderTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        from hrm.models import Profile
        from hrm.permissions import ROLE_DIRECTOR

        self.user = User.objects.create_user('p2admin', 'p2@test.local', 'x')
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.role = ROLE_DIRECTOR
        profile.save()
        self.user.refresh_from_db()
        self.client.force_login(self.user)
        upsert_stock_policy(product_code='SP-UI', min_stock=Decimal('100'))

    def test_stock_policy_page(self):
        from django.urls import reverse

        resp = self.client.get(reverse('san_xuat:stock_policy_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8', 'ignore')
        self.assertIn('SP-UI', body)
        self.assertNotIn('Traceback', body)

    def test_restock_page(self):
        from django.urls import reverse

        resp = self.client.get(reverse('san_xuat:restock_suggestions'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('SP-UI', resp.content.decode('utf-8', 'ignore'))

    def test_create_form_shows_three_methods(self):
        from django.urls import reverse

        body = self.client.get(reverse('san_xuat:plan_overall_create')).content.decode('utf-8', 'ignore')
        for label in ('MTO', 'MTS', 'MPS'):
            self.assertIn(label, body)

    def test_create_mts_plan_via_post(self):
        from django.urls import reverse

        resp = self.client.post(reverse('san_xuat:plan_overall_create'), {
            'name': 'KH MTS qua form',
            'plan_method': SxOverallPlan.METHOD_MTS,
            'date_from': '2026-08-03',
            'date_to': '2026-08-10',
            'mps_bucket': SxOverallPlan.BUCKET_WEEK,
            'apply_netting': 'on',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        plan = SxOverallPlan.objects.filter(name='KH MTS qua form').first()
        self.assertIsNotNone(plan)
        self.assertEqual(plan.plan_method, SxOverallPlan.METHOD_MTS)

    def test_mps_detail_shows_bucket_grid(self):
        from django.urls import reverse

        plan = _plan(
            SxOverallPlan.METHOD_MPS,
            date_from=date(2026, 8, 3),
            date_to=date(2026, 8, 30),
            frozen_until=date(2026, 8, 9),
        )
        load_mps_demand(plan_id=plan.pk, rows=[
            {'product_code': 'SP-UI', 'qty': Decimal('90'), 'bucket_start': date(2026, 8, 17)},
        ])
        body = self.client.get(
            reverse('san_xuat:plan_overall_detail', args=[plan.pk])
        ).content.decode('utf-8', 'ignore')
        self.assertIn('Lịch trình chủ', body)
        self.assertIn('Nhập lịch trình', body)
        self.assertIn('SP-UI', body)

    def test_mts_detail_shows_restock_panel(self):
        from django.urls import reverse

        plan = _plan(SxOverallPlan.METHOD_MTS)
        body = self.client.get(
            reverse('san_xuat:plan_overall_detail', args=[plan.pk])
        ).content.decode('utf-8', 'ignore')
        self.assertIn('Nạp nhu cầu bù tồn', body)

    def test_restock_page_creates_mts_plan(self):
        from django.urls import reverse

        resp = self.client.post(
            reverse('san_xuat:restock_suggestions'),
            {'product_codes': ['SP-UI']},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        plan = SxOverallPlan.objects.filter(plan_method=SxOverallPlan.METHOD_MTS).first()
        self.assertIsNotNone(plan)
        self.assertEqual(
            [ln.product_code for ln in plan.lines.all()], ['SP-UI'],
        )
