"""QC theo tổ Ob: cổng nhập TP đủ tổ + resolve menu /chat-luong/to/."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from hrm.menu_permissions import resolve_menu_from_request
from hrm.submenu_registry import MODULE_SAN_XUAT
from san_xuat.hub_models import (
    SxProductionOrder,
    SxQcInspection,
    SxQcRequest,
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderRoutingLine,
)
from san_xuat.services.gates import check_qc_pass_before_fg, check_qc_pass_before_wip_handover
from san_xuat.services.progress_template import team_slug_for_work_center_code
from san_xuat.services.qc import all_ob_teams_qc_passed, ob_qc_teams


class TeamSlugFromWorkCenterTests(SimpleTestCase):
    def test_maps_standard_codes(self):
        self.assertEqual(team_slug_for_work_center_code("CAT"), "cat")
        self.assertEqual(team_slug_for_work_center_code("IN-EP"), "inep")
        self.assertEqual(team_slug_for_work_center_code("MAY"), "may")
        self.assertEqual(team_slug_for_work_center_code("HT"), "ht")


class QcMenuPathTests(SimpleTestCase):
    def test_team_board_resolves_to_qc(self):
        module, menu = resolve_menu_from_request("/san-xuat/chat-luong/to/may/")
        self.assertEqual(module, MODULE_SAN_XUAT)
        self.assertEqual(menu, "qc")

    def test_standards_resolves_to_qc(self):
        module, menu = resolve_menu_from_request("/san-xuat/chat-luong/tieu-chuan/")
        self.assertEqual(module, MODULE_SAN_XUAT)
        self.assertEqual(menu, "qc")


class ObTeamQcGateTests(TestCase):
    def _order_with_ob(self, *wc_codes):
        order = SxSalesOrder.objects.create(
            code=f"DH-QC-{timezone.now().timestamp()}",
            request_date=date(2026, 8, 1),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        )
        line = SxSalesOrderLine.objects.create(
            order=order,
            product_code="JP-TEE-TEST",
            product_name="Áo test QC",
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
            code=f"LSX-QC-{order.pk}",
            product_code="JP-TEE-TEST",
            product_name="Áo test QC",
            qty=Decimal("10"),
            order_date=date(2026, 8, 1),
            status=SxProductionOrder.STATUS_IN_PROGRESS,
            sales_order=order,
        )
        return order, mo

    def _pass_inspection(self, mo, slug, *, code_suffix):
        req = SxQcRequest.objects.create(
            code=f"YCKT-T-{code_suffix}",
            production_order=mo,
            product_code=mo.product_code,
            product_name=mo.product_name,
            stage_name=slug,
            team_slug=slug,
            qty=Decimal("10"),
            request_date=date(2026, 8, 2),
            status="done",
        )
        return SxQcInspection.objects.create(
            code=f"PKT-T-{code_suffix}",
            qc_request=req,
            inspected_at=date(2026, 8, 2),
            qty_sample=Decimal("5"),
            qty_pass=Decimal("5"),
            qty_fail=Decimal("0"),
            result=SxQcInspection.RESULT_PASS,
            status="done",
        )

    def test_ob_qc_teams_from_routing_work_centers(self):
        _order, mo = self._order_with_ob("CAT", "MAY")
        teams = ob_qc_teams(mo=mo)
        self.assertEqual([t.slug for t in teams], ["cat", "may"])

    def test_one_pass_is_not_enough_when_two_ob_teams(self):
        _order, mo = self._order_with_ob("CAT", "MAY")
        self._pass_inspection(mo, "cat", code_suffix="1")
        ok, missing = all_ob_teams_qc_passed(mo=mo)
        self.assertFalse(ok)
        self.assertTrue(missing)
        gate = check_qc_pass_before_fg(mo=mo)
        self.assertFalse(gate.ok)
        self.assertIn("Ob", gate.message)

    def test_all_ob_teams_pass_opens_fg_gate(self):
        _order, mo = self._order_with_ob("CAT", "MAY")
        self._pass_inspection(mo, "cat", code_suffix="2")
        self._pass_inspection(mo, "may", code_suffix="3")
        ok, missing = all_ob_teams_qc_passed(mo=mo)
        self.assertTrue(ok)
        self.assertEqual(missing, [])
        gate = check_qc_pass_before_fg(mo=mo)
        self.assertTrue(gate.ok)

    def test_generic_pass_without_team_slug_does_not_cover_ob_teams(self):
        _order, mo = self._order_with_ob("CAT")
        req = SxQcRequest.objects.create(
            code="YCKT-T-OLD",
            production_order=mo,
            product_code=mo.product_code,
            qty=Decimal("10"),
            request_date=date(2026, 8, 2),
            status="done",
            team_slug="",
        )
        SxQcInspection.objects.create(
            code="PKT-T-OLD",
            qc_request=req,
            inspected_at=date(2026, 8, 2),
            result=SxQcInspection.RESULT_PASS,
        )
        ok, missing = all_ob_teams_qc_passed(mo=mo)
        self.assertFalse(ok)
        self.assertTrue(missing)

    def test_wip_handover_not_blocked_without_qc(self):
        _order, mo = self._order_with_ob('CAT', 'MAY')
        gate = check_qc_pass_before_wip_handover(mo=mo, from_process='Cắt')
        self.assertTrue(gate.ok)

    def test_qc_steps_do_not_block_mo_completion_pct(self):
        from san_xuat.services.mo_progress import build_mo_progress
        _order, mo = self._order_with_ob('CAT', 'MAY')
        progress = build_mo_progress(mo)
        qc_steps = [s for s in progress.steps if s.key.startswith('qc_')]
        self.assertTrue(qc_steps)
        self.assertTrue(all(s.optional for s in qc_steps))
        self.assertFalse(progress.qc_done)
        self.assertEqual(progress.total_steps, sum(1 for s in progress.steps if not s.optional))
