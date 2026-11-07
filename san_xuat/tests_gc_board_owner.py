"""Don gia cong chi hien tren to cua work center cuoi trong lo trinh."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from san_xuat.hub_models import SxOrderTeamDayPlan, SxSalesOrder, SxSalesOrderPlanStep, SxWorkCenter
from san_xuat.partner_models import GcPartner
from san_xuat.services.goods_progress import _team_columns
from san_xuat.services.team_output_report import _plan_by_team_day, _team_plan_hits
from san_xuat.services.team_work import TeamWorkJob, apply_own_plan_team


class GcBoardSingleTeamTests(TestCase):
    def setUp(self):
        self.old_gc = SxWorkCenter.objects.create(
            code="GC-ONE-OLD", name="Thue ngoai cu", is_active=True,
        )
        self.new_gc = SxWorkCenter.objects.create(
            code="GC-ONE-NEW", name="To dich", is_active=True,
        )
        GcPartner.objects.create(code="GC-ONE-OLD-P", name="Thue ngoai cu", work_center=self.old_gc)
        GcPartner.objects.create(code="GC-ONE-NEW-P", name="To dich", work_center=self.new_gc)
        self.day = date(2026, 8, 10)

    def _order(self, code):
        order = SxSalesOrder.objects.create(
            code=code,
            request_date=date(2026, 8, 3),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status=SxSalesOrder.PLAN_IN_PROGRESS,
        )
        SxSalesOrderPlanStep.objects.create(
            sales_order=order, sequence=10, process_name="Cu", work_center=self.old_gc,
        )
        SxSalesOrderPlanStep.objects.create(
            sales_order=order, sequence=20, process_name="Moi", work_center=self.new_gc,
        )
        return order

    def test_old_gc_board_drops_order_owned_by_later_snapshot(self):
        order = self._order("DH-GC-ONE-BOARD")
        job = TeamWorkJob(mo=SimpleNamespace(sales_order_id=order.pk, status="in_progress"), rows=[])
        old_board = apply_own_plan_team(
            [job],
            team={
                "work_center_code": self.old_gc.code,
                "slug": f"gc-{self.old_gc.pk}",
                "stage_slug": "",
                "is_gc": True,
            },
        )
        new_board = apply_own_plan_team(
            [job],
            team={
                "work_center_code": self.new_gc.code,
                "slug": f"gc-{self.new_gc.pk}",
                "stage_slug": "",
                "is_gc": True,
            },
        )
        self.assertEqual(old_board, [])
        self.assertEqual(new_board, [job])

    def test_sheet_keeps_order_on_destination_and_uses_old_qty_only_when_dest_has_none(self):
        leftover = self._order("DH-GC-ONE-LEFT")
        SxOrderTeamDayPlan.objects.create(
            sales_order=leftover,
            team_slug=f"gc-{self.old_gc.pk}",
            work_center=self.old_gc,
            plan_date=self.day,
            qty=Decimal("12"),
        )
        both = self._order("DH-GC-ONE-BOTH")
        SxOrderTeamDayPlan.objects.create(
            sales_order=both,
            team_slug=f"gc-{self.old_gc.pk}",
            work_center=self.old_gc,
            plan_date=self.day,
            qty=Decimal("9"),
        )
        SxOrderTeamDayPlan.objects.create(
            sales_order=both,
            team_slug=f"gc-{self.new_gc.pk}",
            work_center=self.new_gc,
            plan_date=self.day,
            qty=Decimal("4"),
        )

        old_slug = f"gc-{self.old_gc.pk}"
        new_slug = f"gc-{self.new_gc.pk}"
        old_hits = {oid for _day, oid, _status in _team_plan_hits(old_slug)}
        new_hits = {oid for _day, oid, _status in _team_plan_hits(new_slug)}
        self.assertNotIn(leftover.pk, old_hits)
        self.assertNotIn(both.pk, old_hits)
        self.assertIn(leftover.pk, new_hits)
        self.assertIn(both.pk, new_hits)

        _by_team, _by_stage, listed = _plan_by_team_day(
            _team_columns(), date_from=self.day, date_to=self.day,
        )
        old_ids = {item["id"] for item in listed.get(old_slug, {}).get(self.day, [])}
        new_qty = {item["id"]: item["qty"] for item in listed.get(new_slug, {}).get(self.day, [])}
        self.assertNotIn(leftover.pk, old_ids)
        self.assertNotIn(both.pk, old_ids)
        self.assertEqual(new_qty.get(leftover.pk), Decimal("12"))
        self.assertEqual(new_qty.get(both.pk), Decimal("4"))

    def test_gc_day_plan_without_route_center_stays_off_gc_board(self):
        from san_xuat.services.team_output_report import _sole_gc_team

        hidden = _sole_gc_team(
            "gc-47",
            order_id=259,
            work_center_id=47,
            gc_centers={47: "gc-47"},
            owners={},
            day_centers={259: {4, 47}},
        )
        kept = _sole_gc_team(
            "d25",
            order_id=259,
            work_center_id=4,
            gc_centers={47: "gc-47"},
            owners={},
            day_centers={259: {4, 47}},
        )
        self.assertEqual(hidden, "")
        self.assertEqual(kept, "d25")
