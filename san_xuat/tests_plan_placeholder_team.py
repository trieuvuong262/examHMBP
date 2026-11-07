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

        from san_xuat.services.plan_board import _team_loads_from_order

        row = next(r for r in _team_loads_from_order(order) if r['slug'] == step.board_slug)
        self.assertEqual(row['work_center_id'], self.thue.pk)
        self.assertEqual(row['dept_label'], MAY_LABEL)

    def test_assign_team_moves_lsx_steps_not_ob(self):
        from san_xuat.hub_models import SxMoProcessStep, SxProductionOrder
        from san_xuat.services.plan_board import assign_plan_team

        order = create_sales_order(
            customer_name='KH', request_date=timezone.localdate(),
            lines=[LineInput(product_code='PH', qty=Decimal('10'), product_name='Ao',
                             routing_id=self.routing.pk)],
        )
        order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
        order.save(update_fields=['confirm_status'])
        order.plan_steps.all().delete()
        ensure_order_plan_steps(order)
        step = order.plan_steps.get()
        mo = SxProductionOrder.objects.create(
            code='LSX-PH-1', product_code='PH', qty=Decimal('10'),
            order_date=timezone.localdate(), sales_order=order,
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        mo_step = SxMoProcessStep.objects.create(
            production_order=mo, sequence=10, process_name=step.process_name,
            op_code='SEW_HEM_1008', work_center=self.thue,
        )
        gc = SxWorkCenter.objects.create(
            code='NL-2026-0001', name='50-Phú TV', team_label='50-Phú TV',
            headcount=5, capacity_per_day=Decimal('100'),
        )

        assign_plan_team(
            order_id=order.pk, team_slug=step.board_slug,
            work_center_id=gc.pk, source_work_center_id=self.thue.pk,
        )

        mo_step.refresh_from_db()
        self.assertEqual(mo_step.work_center_id, gc.pk)
        ob = order.lines.get().routing_lines.get()
        self.assertEqual(ob.work_center_id, self.may.pk)

    def test_lsx_built_from_ob_takes_khsx_team(self):
        from san_xuat.hub_models import SxProductionOrder
        from san_xuat.services.plan_board import sync_mo_steps_from_order_line

        order = create_sales_order(
            customer_name='KH', request_date=timezone.localdate(),
            lines=[LineInput(product_code='PH', qty=Decimal('10'), product_name='Ao',
                             routing_id=self.routing.pk)],
        )
        order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
        order.save(update_fields=['confirm_status'])
        order.plan_steps.all().delete()
        ensure_order_plan_steps(order)
        mo = SxProductionOrder.objects.create(
            code='LSX-PH-2', product_code='PH', qty=Decimal('10'),
            order_date=timezone.localdate(), sales_order=order,
            status=SxProductionOrder.STATUS_DRAFT,
        )

        sync_mo_steps_from_order_line(
            mo, order.lines.get(), routing_id=None, planned_by_name={}, hop_by_name={},
        )

        self.assertEqual(
            set(mo.mo_process_steps.values_list('work_center_id', flat=True)), {self.thue.pk},
        )

    def test_gc_team_with_hr_division_uses_gc_progress_slug(self):
        from hrm.models import Department, Division
        from san_xuat.partner_models import GcPartner
        from san_xuat.services.team_division_map import board_slugs_for_work_centers

        dept = Department.objects.create(name='SX Test', sort_order=990)
        div = Division.objects.create(name='MAY (19 CHIẾN LƯỢC)', department=dept, sort_order=1)
        gc = SxWorkCenter.objects.create(
            code='NL-2026-0003', name='44-Minh Nhân TV', team_label='44-Minh Nhân TV', division=div,
        )
        GcPartner.objects.create(code='GC-MN', name='Minh Nhân', work_center=gc)

        self.assertEqual(board_slugs_for_work_centers([gc.pk]), {gc.pk: f'gc-{gc.pk}'})

    def test_gc_day_plan_team_finds_lsx_steps_on_khsx_team(self):
        from san_xuat.hub_models import SxMoProcessStep, SxOrderTeamDayPlan, SxProductionOrder
        from san_xuat.partner_models import GcPartner
        from san_xuat.services.order_progress_sheet import progress_steps_for_team
        from san_xuat.services.team_division_map import gc_team_from_slug

        order = create_sales_order(
            customer_name='KH', request_date=timezone.localdate(),
            lines=[LineInput(product_code='PH', qty=Decimal('10'), product_name='Ao',
                             routing_id=self.routing.pk)],
        )
        order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
        order.save(update_fields=['confirm_status'])
        order.plan_steps.all().delete()
        ensure_order_plan_steps(order)
        step = order.plan_steps.get()
        mo = SxProductionOrder.objects.create(
            code='LSX-PH-3', product_code='PH', qty=Decimal('10'),
            order_date=timezone.localdate(), sales_order=order,
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        SxMoProcessStep.objects.create(
            production_order=mo, sequence=10, process_name=step.process_name,
            op_code='SEW_HEM_1008', work_center=self.thue,
        )
        gc = SxWorkCenter.objects.create(code='NL-2026-0007', name='44-Minh Nhân TV')
        GcPartner.objects.create(code='GC-MN2', name='Minh Nhân', work_center=gc)
        SxOrderTeamDayPlan.objects.create(
            sales_order=order, team_slug=step.board_slug, work_center=gc,
            plan_date=timezone.localdate(), qty=Decimal('10'),
        )

        steps = progress_steps_for_team(mo, gc_team_from_slug(f'gc-{gc.pk}'))

        self.assertEqual([s.label for s in steps], [step.process_name])