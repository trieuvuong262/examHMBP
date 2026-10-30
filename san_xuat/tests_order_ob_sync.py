"""Đồng bộ OB/BOM đơn hàng -> KHSX / LSX theo các quyết định đã chốt."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from san_xuat.hub_models import (
    SxMoProcessAssignee,
    SxMoProcessStep,
    SxProductionOrder,
    SxProductionStat,
    SxSalesOrder,
    SxSalesOrderLine,
)
from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRouting, SxRoutingLine
from san_xuat.services.order_routing import (
    OrderRoutingError,
    _match_mo_step,
    apply_order_routing_edits,
    assert_no_duplicate_product_lines,
    order_npl_deferred,
    sync_active_mos_from_order,
    update_order_line_bom_overrides,
)
from san_xuat.services.sales_orders import LineInput, create_sales_order


class OrderObSyncTests(TestCase):
    def setUp(self):
        group = SxOperationGroup.objects.create(code='SEW', name='May')
        self.ops = []
        for code, name in (('SEW-1', 'May suon'), ('SEW-2', 'May vai'), ('SEW-3', 'Vat so')):
            self.ops.append(SxOperation.objects.create(
                group=group, op_code=code, op_rev='R01', name_vi=name,
                base_smv_min=Decimal('1'), status=SxOperation.STATUS_APPROVED,
            ))
        self.routing = SxRouting.objects.create(
            routing_id='OBT-R01', style_code='OBT', style_name='T', routing_rev='R01',
            is_active=True, approval_status=SxRouting.APPROVAL_APPROVED,
        )
        for i, op in enumerate(self.ops[:2], start=1):
            SxRoutingLine.objects.create(
                routing=self.routing, seq_no=i, operation=op, op_code=op.op_code,
                op_rev=op.op_rev, op_name_vi=op.name_vi,
                library_unit_smv=Decimal('60'), applied_unit_smv=Decimal('60'),
            )
        self.order = create_sales_order(
            customer_name='KH', request_date=timezone.localdate(),
            lines=[LineInput(product_code='OBT', qty=Decimal('10'), product_name='Ao',
                             routing_id=self.routing.pk)],
        )
        self.line = self.order.lines.get()

    def _mo(self, *, seq_offset=0, with_code=True):
        mo = SxProductionOrder.objects.create(
            code=f'LSX-T{seq_offset}-{with_code}', product_code='OBT', qty=Decimal('10'),
            order_date=timezone.localdate(), sales_order=self.order,
            status=SxProductionOrder.STATUS_IN_PROGRESS,
        )
        for i, snap in enumerate(self.line.routing_lines.order_by('seq_no'), start=1):
            SxMoProcessStep.objects.create(
                production_order=mo, sequence=i * 10 + seq_offset,
                process_name=snap.op_name_vi,
                op_code=snap.op_code if with_code else '',
                applied_unit_smv=snap.applied_unit_smv,
            )
        return mo

    def _snap(self, code):
        return self.line.routing_lines.get(op_code=code)

    def test_match_by_code_then_name(self):
        mo = self._mo(seq_offset=5, with_code=False)
        hit = _match_mo_step(list(mo.mo_process_steps.all()),
                             {'op_code': 'X', 'process_name': 'may  SUON'})
        self.assertEqual(hit.process_name, 'May suon')
        mo2 = self._mo(seq_offset=7)
        hit2 = _match_mo_step(list(mo2.mo_process_steps.all()),
                              {'op_code': 'SEW-2', 'process_name': 'khac'})
        self.assertEqual(hit2.process_name, 'May vai')

    def test_smv_update_matches_despite_different_sequence(self):
        mo = self._mo(seq_offset=3)
        apply_order_routing_edits(
            self.line, updates=[{'pk': self._snap('SEW-1').pk, 'applied_unit_smv': '90'}],
        )
        sync_active_mos_from_order(self.order)
        self.assertEqual(mo.mo_process_steps.count(), 2)
        self.assertEqual(
            mo.mo_process_steps.get(op_code='SEW-1').applied_unit_smv, Decimal('90.0000'),
        )

    def test_done_step_keeps_smv_but_renames(self):
        mo = self._mo()
        step = mo.mo_process_steps.get(op_code='SEW-1')
        step.status = SxMoProcessStep.STATUS_DONE
        step.save()
        snap = self._snap('SEW-1')
        snap.applied_unit_smv = Decimal('99')
        snap.op_name_vi = 'May suon moi'
        snap.save()
        sync_active_mos_from_order(self.order)
        step.refresh_from_db()
        self.assertEqual(step.applied_unit_smv, Decimal('60.0000'))
        self.assertEqual(step.process_name, 'May suon moi')

    def test_add_operation_creates_mo_step(self):
        mo = self._mo()
        apply_order_routing_edits(self.line, adds=[{'op_code': 'SEW-3', 'op_rev': 'R01'}])
        sync_active_mos_from_order(self.order)
        self.assertEqual(mo.mo_process_steps.count(), 3)
        self.assertTrue(mo.mo_process_steps.filter(op_code='SEW-3').exists())

    def test_delete_operation_without_output_removes_step(self):
        mo = self._mo()
        apply_order_routing_edits(self.line, deletes=[self._snap('SEW-2').pk])
        sync_active_mos_from_order(self.order)
        self.assertFalse(mo.mo_process_steps.filter(op_code='SEW-2').exists())

    def test_delete_operation_with_output_flags_step(self):
        mo = self._mo()
        SxProductionStat.objects.create(
            code='TK-1', production_order=mo, stat_date=timezone.localdate(),
            process_name='May vai', qty_good=Decimal('3'),
        )
        apply_order_routing_edits(self.line, deletes=[self._snap('SEW-2').pk])
        sync_active_mos_from_order(self.order)
        self.assertTrue(mo.mo_process_steps.get(op_code='SEW-2').removed_from_ob)

    def test_delete_operation_with_assignee_flags_step(self):
        mo = self._mo()
        user = get_user_model().objects.create_user(username='u-ob', password='x')
        step = mo.mo_process_steps.get(op_code='SEW-2')
        SxMoProcessAssignee.objects.create(mo_process_step=step, user=user)
        apply_order_routing_edits(self.line, deletes=[self._snap('SEW-2').pk])
        sync_active_mos_from_order(self.order)
        step.refresh_from_db()
        self.assertTrue(step.removed_from_ob)

    def test_done_mo_not_touched(self):
        mo = self._mo()
        mo.status = SxProductionOrder.STATUS_DONE
        mo.save()
        apply_order_routing_edits(self.line, deletes=[self._snap('SEW-2').pk])
        sync_active_mos_from_order(self.order)
        self.assertTrue(mo.mo_process_steps.filter(op_code='SEW-2').exists())

    def test_duplicate_product_lines_blocked(self):
        assert_no_duplicate_product_lines(self.line)
        SxSalesOrderLine.objects.create(order=self.order, product_code='OBT', qty=Decimal('5'))
        with self.assertRaises(OrderRoutingError):
            assert_no_duplicate_product_lines(self.line)

    def test_draft_bom_saved_without_npl(self):
        self.assertEqual(self.order.confirm_status, SxSalesOrder.CONFIRM_DRAFT)
        self.assertTrue(order_npl_deferred(self.order))
        rows = [{'material_code': 'NPL-A', 'material_name': 'Chi', 'unit': 'cuon',
                 'qty': '2', 'qty_std': '2', 'qty_mode': 'qty'}]
        update_order_line_bom_overrides(self.line, rows=rows)
        self.line.refresh_from_db()
        self.assertEqual(self.line.bom_line_overrides[0]['material_code'], 'NPL-A')
        self.assertFalse(self.order.npl_lines.exists())

    def test_ob_sync_marks_route_sheet_dirty(self):
        """Thêm CĐ trên đơn -> bảng KHSX (SxRouteSheet) phải được tính lại."""
        from unittest import mock

        from san_xuat.services.order_routing import sync_order_plan_steps_from_ob

        self.order.confirm_status = SxSalesOrder.CONFIRM_CONFIRMED
        self.order.save(update_fields=['confirm_status'])
        apply_order_routing_edits(self.line, adds=[{'op_code': 'SEW-3', 'op_rev': 'R01'}])
        with mock.patch('san_xuat.services.route_sheet.mark_route_sheet_dirty') as dirty:
            n = sync_order_plan_steps_from_ob(self.order)
        self.assertEqual(n, 3)
        dirty.assert_any_call(self.order.pk)