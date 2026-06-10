from decimal import Decimal

from django.test import SimpleTestCase

from kho_npl.templatetags.npl_extras import format_npl_qty, npl_qty, npl_qty_with_unit


class NplQtyFormatTests(SimpleTestCase):
    def test_integer_without_decimals(self):
        self.assertEqual(format_npl_qty(Decimal('500000')), '500000')
        self.assertEqual(format_npl_qty(Decimal('500000.000')), '500000')
        self.assertEqual(npl_qty(Decimal('100')), '100')

    def test_fractional_with_comma(self):
        self.assertEqual(format_npl_qty(Decimal('487.5')), '487,5')
        self.assertEqual(format_npl_qty(Decimal('0.125')), '0,125')
        self.assertEqual(format_npl_qty(Decimal('100.500')), '100,5')

    def test_none_and_empty(self):
        self.assertEqual(format_npl_qty(None), '—')
        self.assertEqual(format_npl_qty(''), '—')

    def test_qty_with_unit(self):
        class Unit:
            code = 'met'
            name = 'Mét'

        self.assertEqual(npl_qty_with_unit(Decimal('500000'), Unit()), '500000 met')
        self.assertEqual(npl_qty_with_unit(Decimal('12.5'), Unit()), '12,5 met')
