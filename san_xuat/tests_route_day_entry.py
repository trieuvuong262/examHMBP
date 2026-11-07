from decimal import Decimal

from django.test import SimpleTestCase

from san_xuat.services.planning import PlanningError
from san_xuat.views_hub import _merge_route_day_qty, _parse_route_size_qtys


class RouteDayEntryDraftTests(SimpleTestCase):
    def test_parse_size_qtys_skips_invalid_rows(self):
        rows = _parse_route_size_qtys([
            {"size": "M", "qty": "12"},
            "khong phai dong",
            {"size": "L", "qty": "sai"},
        ])
        self.assertEqual(rows, [("M", Decimal("12")), ("L", Decimal("0"))])

    def test_parse_rejects_non_list(self):
        with self.assertRaises(PlanningError):
            _parse_route_size_qtys({"size": "M"})

    def test_merge_keeps_later_entries_and_revisions(self):
        merged = _merge_route_day_qty(
            {
                "action": "route_day_qty",
                "team_slug": "may",
                "sizes": [{"size": "M", "qty": "10"}],
                "entries": [{"sizes": [{"size": "M", "qty": "10"}]}],
                "revisions": [],
            },
            {
                "action": "route_day_qty",
                "team_slug": "MAY",
                "sizes": [{"size": "M", "qty": "8"}, {"size": "L", "qty": "3"}],
                "entries": [{"sizes": [{"size": "L", "qty": "3"}], "edited_by": "An"}],
                "revisions": [{"key": "log:4", "sizes": [{"size": "M", "qty": "8", "origin": "10"}]}],
            },
        )
        self.assertEqual(merged["team_slug"], "may")
        self.assertEqual(merged["entries"][0]["edited_by"], "An")
        self.assertEqual(merged["revisions"][0]["key"], "log:4")
        self.assertEqual(
            [(row["size"], row["qty"]) for row in merged["sizes"]],
            [("M", "8"), ("L", "3")],
        )
