from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from san_xuat.hub_models import SxSalesOrder
from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRouting, SxRoutingLine
from san_xuat.services.order_routing import (
    assert_order_ready_to_confirm,
    seed_order_line_routing,
    upsert_order_routing_line,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.sales_orders import LineInput, confirm_sales_order, create_sales_order


class OrderRoutingTests(TestCase):
    def setUp(self):
        self.group = SxOperationGroup.objects.create(code='SEW', name='May')
        self.op = SxOperation.objects.create(
            group=self.group,
            op_code='SEW-1001',
            op_rev='R01',
            name_vi='May suon',
            base_smv_min=Decimal('1.2000'),
            status=SxOperation.STATUS_APPROVED,
        )
        self.routing = SxRouting.objects.create(
            routing_id='SPTEST-R01',
            style_code='SPTEST',
            style_name='Test',
            routing_rev='R01',
            is_active=True,
            approval_status=SxRouting.APPROVAL_APPROVED,
        )
        SxRoutingLine.objects.create(
            routing=self.routing,
            seq_no=1,
            operation=self.op,
            op_code=self.op.op_code,
            op_rev=self.op.op_rev,
            op_name_vi=self.op.name_vi,
            library_unit_smv=Decimal('1.2000'),
            applied_unit_smv=Decimal('1.2000'),
        )

    def _order(self, *, with_routing=True) -> SxSalesOrder:
        return create_sales_order(
            customer_name='KH Test',
            request_date=timezone.localdate(),
            lines=[
                LineInput(
                    product_code='SPTEST',
                    qty=Decimal('10'),
                    product_name='Ao test',
                    routing_id=self.routing.pk if with_routing else None,
                )
            ],
        )

    def test_seed_copies_applied_smv(self):
        order = self._order()
        line = order.lines.get()
        self.assertEqual(line.routing_id, self.routing.pk)
        snap = line.routing_lines.get()
        self.assertEqual(snap.op_code, 'SEW-1001')
        self.assertEqual(snap.applied_unit_smv, Decimal('1.2000'))
        self.assertEqual(snap.library_unit_smv, Decimal('1.2000'))

    def test_confirm_requires_routing(self):
        order = self._order(with_routing=False)
        with self.assertRaises(PlanningError) as ctx:
            confirm_sales_order(order_id=order.pk)
        self.assertIn('routing', str(ctx.exception).lower())

    def test_upsert_does_not_change_master(self):
        order = self._order()
        line = order.lines.get()
        snap = line.routing_lines.get()
        upsert_order_routing_line(
            order_line=line,
            line_pk=snap.pk,
            op_code=snap.op_code,
            op_rev=snap.op_rev,
            op_name_vi=snap.op_name_vi,
            applied_unit_smv=Decimal('2.0000'),
            library_unit_smv=snap.library_unit_smv,
            qty_per_garment=snap.qty_per_garment,
        )
        snap.refresh_from_db()
        self.assertEqual(snap.applied_unit_smv, Decimal('2.0000'))
        master = self.routing.lines.get()
        self.assertEqual(master.applied_unit_smv, Decimal('1.2000'))

    def test_high_variance_blocks_confirm(self):
        order = self._order()
        line = order.lines.get()
        snap = line.routing_lines.get()
        snap.applied_unit_smv = Decimal('2.0000')
        snap.variance_explanation = ''
        snap.save()
        with self.assertRaises(PlanningError) as ctx:
            assert_order_ready_to_confirm(order)
        self.assertIn('15', str(ctx.exception))

    def test_reseed_from_master(self):
        order = self._order()
        line = order.lines.get()
        line.routing_lines.all().delete()
        n = seed_order_line_routing(line)
        self.assertEqual(n, 1)
        self.assertEqual(line.routing_lines.count(), 1)
    def test_gtkh_uses_applied_smv(self):
        from san_xuat.services.costing import compute_costing_for_sales_line
        from san_xuat.services.plan_costing import build_order_sheet_from_kv

        order = self._order()
        line = order.lines.get()
        snap = line.routing_lines.get()
        snap.applied_unit_smv = Decimal('2.0000')
        snap.qty_per_garment = Decimal('1')
        snap.price_factor = Decimal('1000')
        snap.total_unit_price = Decimal('0')
        snap.recompute()
        snap.save()

        costing = compute_costing_for_sales_line(line)
        self.assertEqual(costing.labor_cost, Decimal('2000.00'))

        today = timezone.localdate()
        sheet = build_order_sheet_from_kv(
            name='GTKH SMV test',
            date_from=today,
            date_to=today,
            kv_order_code=order.code,
        )
        cost_line = sheet.lines.get()
        unit = costing.total_cost.quantize(Decimal('0.01'))
        self.assertEqual(cost_line.unit_cost, unit)
        self.assertEqual(cost_line.qty, Decimal('10.00'))
        self.assertEqual(cost_line.line_cost, (unit * Decimal('10')).quantize(Decimal('0.01')))
