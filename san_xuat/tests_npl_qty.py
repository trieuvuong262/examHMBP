"""Cong thuc mua va QC — khong can database."""

from decimal import Decimal

from django.test import SimpleTestCase

from san_xuat.services.npl_qty import available_stock_increase, buy_qty, qty_still_due


class NplQtyTests(SimpleTestCase):
    def test_buy_at_most_net_shortage(self):
        self.assertEqual(buy_qty(required=1000, available=200, inbound=300), Decimal("500"))

    def test_defects_do_not_complete_the_order(self):
        due = qty_still_due(ordered=1000, qc_pass=970, qc_fail=30, closed=0, received=1000)
        self.assertEqual(due, Decimal("30"))
        self.assertEqual(available_stock_increase(qc_pass=970), Decimal("970"))

    def test_short_receipt_stays_open_until_closed(self):
        self.assertEqual(
            qty_still_due(ordered=500, qc_pass=450, qc_fail=0, closed=0, received=450),
            Decimal("50"),
        )
        self.assertEqual(
            qty_still_due(ordered=500, qc_pass=450, qc_fail=0, closed=50, received=450),
            Decimal("0"),
        )

    def test_only_passed_qty_increases_available_stock(self):
        self.assertEqual(available_stock_increase(qc_pass=90), Decimal("90"))
        self.assertEqual(available_stock_increase(qc_pass=0), Decimal("0"))

    def test_legacy_receipt_without_qc_counts_as_received(self):
        self.assertEqual(
            qty_still_due(ordered=100, qc_pass=0, qc_fail=0, closed=0, received=100),
            Decimal("0"),
        )
