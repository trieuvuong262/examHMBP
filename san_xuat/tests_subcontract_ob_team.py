"""Thue GC theo to Ob — khong mac dinh theu, khong bat buoc moi lenh."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from hrm.menu_permissions import resolve_menu_from_request
from hrm.submenu_registry import MODULE_SAN_XUAT
from san_xuat.hub_models import (
    SxProductionOrder,
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderRoutingLine,
)
from san_xuat.services.phase3 import Phase3Error, create_subcontract_order
from san_xuat.services.qc import ob_team_options


class SubcontractMenuPathTests(SimpleTestCase):
    def test_thue_gia_cong_resolves_to_subcontract(self):
        module, menu = resolve_menu_from_request("/san-xuat/thue-gia-cong/")
        self.assertEqual(module, MODULE_SAN_XUAT)
        self.assertEqual(menu, "subcontract")


class SubcontractObTeamTests(TestCase):
    def _order_with_ob(self, *wc_codes):
        order = SxSalesOrder.objects.create(
            code=f"DH-GC-{timezone.now().timestamp()}",
            request_date=date(2026, 8, 1),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        line = SxSalesOrderLine.objects.create(
            order=order,
            product_code="JP-TEE-GC",
            product_name="Ao test GC",
            qty=Decimal("10"),
        )
        for i, code in enumerate(wc_codes, start=1):
            SxSalesOrderRoutingLine.objects.create(
                sales_order_line=line,
                seq_no=i,
                op_code=f"OP-{code}-{i}",
                op_name_vi=code,
                work_center_code=code,
            )
        mo = SxProductionOrder.objects.create(
            code=f"LSX-GC-{order.pk}",
            product_code="JP-TEE-GC",
            product_name="Ao test GC",
            qty=Decimal("10"),
            order_date=date(2026, 8, 1),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
            sales_order=order,
        )
        return mo

    def test_ob_options_follow_routing_not_six_teams(self):
        mo = self._order_with_ob("CAT", "MAY")
        slugs = [t["slug"] for t in ob_team_options(mo=mo)]
        self.assertEqual(slugs, ["cat", "may"])
        self.assertNotIn("theu", slugs)

    def test_gc_rejects_team_not_on_ob(self):
        mo = self._order_with_ob("CAT", "MAY")
        with self.assertRaises(Phase3Error) as ctx:
            create_subcontract_order(
                vendor_name="NCC Test",
                product_code=mo.product_code,
                qty=Decimal("2"),
                production_order_id=mo.pk,
                team_slug="theu",
            )
        self.assertIn("Ob", str(ctx.exception))

    def test_gc_uses_selected_ob_team_not_theu(self):
        mo = self._order_with_ob("CAT", "MAY")
        item = create_subcontract_order(
            vendor_name="NCC Test",
            product_code=mo.product_code,
            qty=Decimal("2"),
            production_order_id=mo.pk,
            team_slug="may",
        )
        self.assertEqual(item.team_slug, "may")
        self.assertEqual(item.team_label, "May")
        self.assertNotEqual(item.team_slug, "theu")

    def test_create_gc_without_out_lines_ok(self):
        mo = self._order_with_ob("MAY")
        item = create_subcontract_order(
            vendor_name="NCC Test",
            product_code=mo.product_code,
            qty=Decimal("2"),
            production_order_id=mo.pk,
            team_slug="may",
        )
        self.assertEqual(item.team_slug, "may")
        self.assertEqual(item.material_lines.count(), 0)

    def test_receive_goods_closes_team(self):
        from san_xuat.hub_models import SxTeamWorkClose
        from san_xuat.services.phase3 import receive_subcontract_goods
        from san_xuat.services.team_work import is_team_job_closed

        mo = self._order_with_ob("MAY")
        item = create_subcontract_order(
            vendor_name="NCC Test",
            product_code=mo.product_code,
            qty=Decimal("2"),
            production_order_id=mo.pk,
            team_slug="may",
        )
        item = receive_subcontract_goods(order_id=item.pk, qty_received=Decimal("2"))
        self.assertEqual(item.status, item.STATUS_DONE)
        self.assertTrue(is_team_job_closed(mo_id=mo.pk, team_slug="may"))
        self.assertTrue(SxTeamWorkClose.objects.filter(production_order=mo, team_slug="may").exists())

    def test_assign_blocked_when_gc_active(self):
        from san_xuat.services.planning import PlanningError
        from san_xuat.services.team_work import assign_team_work

        mo = self._order_with_ob("MAY")
        create_subcontract_order(
            vendor_name="NCC Test",
            product_code=mo.product_code,
            qty=Decimal("2"),
            production_order_id=mo.pk,
            team_slug="may",
        )
        with self.assertRaises(PlanningError) as ctx:
            assign_team_work(mo_id=mo.pk, process_key="may_rap_vai", user_ids=[], team_slug="may")
        self.assertIn("gia công", str(ctx.exception).lower())

