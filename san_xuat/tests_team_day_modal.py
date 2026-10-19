from datetime import date

from django.test import TestCase

from san_xuat.hub_models import SxSalesOrder, SxTeamDayModalRank
from san_xuat.services.team_output_report import _join_names, reorder_team_day_orders


class TeamDayModalRankTests(TestCase):
    def test_product_label_is_name_only(self):
        self.assertEqual(_join_names(["  Ao thun  ", "Ao thun", "Quan"]), "Ao thun, Quan")
        self.assertEqual(_join_names(["", "   "]), "")

    def test_reorder_keeps_route_rank(self):
        first = SxSalesOrder.objects.create(
            code="DH-MODAL-A",
            request_date=date(2026, 10, 1),
            plan_rank=3,
            plan_priority=SxSalesOrder.PRIORITY_URGENT,
        )
        second = SxSalesOrder.objects.create(
            code="DH-MODAL-B",
            request_date=date(2026, 10, 1),
            plan_rank=1,
            plan_priority=SxSalesOrder.PRIORITY_NORMAL,
        )
        day = date(2026, 10, 19)
        updated = reorder_team_day_orders(
            team_slug="d12",
            plan_date=day,
            ordered_ids=[second.pk, first.pk],
        )
        self.assertEqual(updated, 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.plan_rank, 3)
        self.assertEqual(second.plan_rank, 1)
        ranks = list(
            SxTeamDayModalRank.objects.filter(team_slug="d12", plan_date=day)
            .order_by("sort_order")
            .values_list("sales_order_id", flat=True)
        )
        self.assertEqual(ranks, [second.pk, first.pk])

        reorder_team_day_orders(
            team_slug="d12",
            plan_date=day,
            ordered_ids=[first.pk, second.pk],
        )
        first.refresh_from_db()
        ranks = list(
            SxTeamDayModalRank.objects.filter(team_slug="d12", plan_date=day)
            .order_by("sort_order")
            .values_list("sales_order_id", flat=True)
        )
        self.assertEqual(ranks, [first.pk, second.pk])
        self.assertEqual(first.plan_rank, 3)
        self.assertEqual(second.plan_rank, 1)
