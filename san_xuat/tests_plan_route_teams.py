"""Lo trinh KHSX theo to: span, hop, keo mot to khong doi to khac."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from san_xuat.hub_models import (
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderRoutingLine,
    SxWorkCenter,
)
from san_xuat.services.plan_board import (
    PLAN_SHIFT_MINUTES,
    _team_loads_from_order,
    reschedule_order_team_start,
    team_khsx_spans,
)


def _wc(code, name):
    obj, _ = SxWorkCenter.objects.get_or_create(
        code=code,
        defaults={'name': name, 'is_active': True},
    )
    return obj


class TeamKhsxSpanTests(TestCase):
    def setUp(self):
        self.wc_cat = _wc('CAT', 'Cat')
        self.wc_may = _wc('MAY', 'May')

    def _order(self, *, hop_count=0, code=None):
        order = SxSalesOrder.objects.create(
            code=code or f'DH-RT-{timezone.now().timestamp()}',
            request_date=date(2026, 8, 3),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status=SxSalesOrder.PLAN_QUEUED,
        )
        line = SxSalesOrderLine.objects.create(
            order=order,
            product_code='JP-TEE-RT',
            product_name='Ao test lo trinh',
            qty=Decimal('1'),
        )
        smv_sec = PLAN_SHIFT_MINUTES * Decimal('60')
        SxSalesOrderRoutingLine.objects.create(
            sales_order_line=line,
            seq_no=1,
            op_code='OP-CAT',
            op_name_vi='Cat',
            work_center=self.wc_cat,
            work_center_code='CAT',
            applied_unit_smv=smv_sec,
            library_unit_smv=smv_sec,
            total_operation_smv=smv_sec,
            count_minutes=Decimal(str(hop_count)),
            transfer_minutes=Decimal('0'),
        )
        SxSalesOrderRoutingLine.objects.create(
            sales_order_line=line,
            seq_no=2,
            op_code='OP-MAY',
            op_name_vi='May',
            work_center=self.wc_may,
            work_center_code='MAY',
            applied_unit_smv=smv_sec,
            library_unit_smv=smv_sec,
            total_operation_smv=smv_sec,
        )
        return order

    def test_loads_two_teams_with_hop_on_source(self):
        order = self._order(hop_count=30)
        loads = _team_loads_from_order(order)
        slugs = [r['slug'] for r in loads]
        self.assertEqual(slugs, ['cat', 'may'])
        by_slug = {r['slug']: r for r in loads}
        self.assertEqual(by_slug['cat']['work_minutes'], PLAN_SHIFT_MINUTES)
        self.assertEqual(by_slug['cat']['buffer_minutes'], Decimal('30.00'))
        self.assertEqual(by_slug['may']['work_minutes'], PLAN_SHIFT_MINUTES)
        self.assertEqual(by_slug['may']['buffer_minutes'], Decimal('0.00'))

    def test_default_sequential_no_overlap(self):
        order = self._order()
        spans = team_khsx_spans(order)
        by_slug = {s.slug: s for s in spans}
        self.assertEqual(by_slug['cat'].start, date(2026, 8, 3))
        self.assertEqual(by_slug['cat'].end, date(2026, 8, 3))
        self.assertEqual(by_slug['may'].start, date(2026, 8, 4))
        self.assertEqual(by_slug['may'].end, date(2026, 8, 4))

    def test_hop_extends_source_team_then_next_starts_after(self):
        order = self._order(hop_count=30)
        spans = team_khsx_spans(order)
        by_slug = {s.slug: s for s in spans}
        self.assertEqual(by_slug['cat'].start, date(2026, 8, 3))
        self.assertEqual(by_slug['cat'].end, date(2026, 8, 4))
        self.assertEqual(by_slug['may'].start, date(2026, 8, 5))

    def test_drag_one_team_does_not_move_the_other(self):
        order = self._order()
        before = {s.slug: (s.start, s.end) for s in team_khsx_spans(order)}
        reschedule_order_team_start(
            order_id=order.pk,
            team_slug='may',
            start_date=date(2026, 8, 12),
        )
        after = {s.slug: s for s in team_khsx_spans(order)}
        self.assertEqual(after['cat'].start, before['cat'][0])
        self.assertEqual(after['cat'].end, before['cat'][1])
        self.assertEqual(after['may'].start, date(2026, 8, 12))
        self.assertNotEqual(after['may'].start, before['may'][0])
        dates = set(
            order.plan_steps.select_related('work_center').values_list('planned_date', flat=True)
        )
        self.assertIn(date(2026, 8, 3), dates)
        self.assertIn(date(2026, 8, 12), dates)


class RescheduleRouteViewTests(TestCase):
    def setUp(self):
        self.wc_cat = _wc('CAT', 'Cat')
        self.wc_may = _wc('MAY', 'May')
        User = get_user_model()
        self.user, _created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'route@example.com'},
        )
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.is_active = True
        self.user.set_password('x')
        self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

    def _order(self):
        order = SxSalesOrder.objects.create(
            code=f'DH-RTV-{timezone.now().timestamp()}',
            request_date=date(2026, 8, 3),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status=SxSalesOrder.PLAN_QUEUED,
        )
        line = SxSalesOrderLine.objects.create(
            order=order,
            product_code='JP-TEE-RTV',
            qty=Decimal('1'),
        )
        smv_sec = PLAN_SHIFT_MINUTES * Decimal('60')
        SxSalesOrderRoutingLine.objects.create(
            sales_order_line=line,
            seq_no=1,
            op_code='OP-CAT',
            op_name_vi='Cat',
            work_center=self.wc_cat,
            work_center_code='CAT',
            applied_unit_smv=smv_sec,
            total_operation_smv=smv_sec,
        )
        SxSalesOrderRoutingLine.objects.create(
            sales_order_line=line,
            seq_no=2,
            op_code='OP-MAY',
            op_name_vi='May',
            work_center=self.wc_may,
            work_center_code='MAY',
            applied_unit_smv=smv_sec,
            total_operation_smv=smv_sec,
        )
        return order

    def test_post_json_reschedule_team(self):
        order = self._order()
        url = reverse('san_xuat:plan_board') + '?mode=list&tab=route'
        resp = self.client.post(
            url,
            {
                'action': 'reschedule_route',
                'order_id': str(order.pk),
                'start_date': '2026-08-18',
                'team_slug': 'cat',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('team_slug'), 'cat')
        self.assertEqual(data.get('start_date'), '2026-08-18')
        spans = {s.slug: s for s in team_khsx_spans(SxSalesOrder.objects.get(pk=order.pk))}
        self.assertEqual(spans['cat'].start, date(2026, 8, 18))
        self.assertEqual(spans['may'].start, date(2026, 8, 4))
