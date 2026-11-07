"""Tổ chờ của nhóm (THUÊ NGOÀI) chỉ gán trên KHSX — OB đơn giữ bộ phận hồ sơ thiết kế."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from san_xuat.hub_models import SxSalesOrder, SxWorkCenter
from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRouting, SxRoutingLine
from san_xuat.services import capacity_from_hrm
from san_xuat.services.plan_route import ensure_order_plan_steps
from san_xuat.services.sales_orders import LineInput, create_sales_order

MAY_LABEL = 'MAY (152A VĨNH LỘC)'


class PlaceholderTeamTests(TestCase):
    def setUp(self):
        capacity_from_hrm._tls.__dict__.clear()
        self.may = SxWorkCenter.objects.create(
            code='HRD-25', name=MAY_LABEL, team_label=MAY_LABEL,
            headcount=10, capacity_per_day=Decimal('100'),
        )
        self.thue = SxWorkCenter.objects.create(
            code='NL-2026-0011', name='THUÊ NGOÀI', team_label='THUÊ NGOÀI',
            headcount=1, capacity_per_day=Decimal('100'),
        )
        self.group = SxOperationGroup.objects.create(
            code='SEW_HEM', name='May lai', process_stage_label=MAY_LABEL,
            default_work_center=self.thue,
        )
        op = SxOperation.objects.create(
            group=self.group, op_code='SEW_HEM_1008', op_rev='R01', name_vi='Kansai lai áo',
            base_smv_min=Decimal('1'), status=SxOperation.STATUS_APPROVED,
        )
        self.routing = SxRouting.objects.create(
            routing_id='PH-R01', style_code='PH', style_name='T', routing_rev='R01',
            is_active=True, approval_status=SxRouting.APPROVAL_APPROVED,
        )
        SxRoutingLine.objects.create(
            routing=self.routing, seq_no=1, operation=op, op_code=op.op_code,
            op_rev='R01', op_name_vi=op.name_vi, group_code='SEW_HEM',
            library_unit_smv=Decimal('60'), applied_unit_smv=Decimal('60'),
            work_center=self.may, work_center_code=MAY_LABEL,
        )

    def tearDown(self):
        capacity_from_hrm._tls.__dict__.clear()

    def test_department_resolvers_ignore_placeholder(self):
        self.assertEqual(capacity_from_hrm.work_center_for_operation_group(self.group), self.may)
        self.assertEqual(
            capacity_from_hrm.placeholder_team_for_operation_group(self.group), self.thue,
        )

    def test_new_order_keeps_ob_department_and_pins_khsx(self):
        order = create_sales_order(
            customer_name='KH', request_date=timezone.localdate(),
            lines=[LineInput(product_code='PH', qty=Decimal('10'), product_name='Ao',
                             routing_id=self.routing.pk)],
        )
        ob = order.lines.get().routing_lines.get()
        self.assertEqual(ob.work_center_id, self.may.pk)

        order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
        order.save(update_fields=['confirm_status'])
        order.plan_steps.all().delete()
        ensure_order_plan_steps(order)

        step = order.plan_steps.get()
        self.assertEqual(step.work_center_id, self.thue.pk)
        self.assertEqual(step.dept_label, MAY_LABEL)
        self.assertTrue(step.board_slug)
        ob.refresh_from_db()
        self.assertEqual(ob.work_center_id, self.may.pk)
