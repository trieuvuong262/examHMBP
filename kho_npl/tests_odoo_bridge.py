"""Unit tests cho bridge NPL -> Odoo (khong can Odoo that)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from kho_npl.models import Material, MaterialCategory, Unit
from kho_npl.odoo_bridge import (
    NPL_CATEGORY_ROOT,
    NPL_UOM_MAP,
    NPL_WAREHOUSE_CODE,
    build_material_vals,
    map_uom_search_name,
)


class NplUomMapTests(TestCase):
    def test_meter_codes(self):
        self.assertEqual(map_uom_search_name('met'), 'm')
        self.assertEqual(map_uom_search_name('tm-ms'), 'm')
        self.assertEqual(map_uom_search_name('TM-MS3'), 'm')

    def test_units_fallback(self):
        self.assertEqual(map_uom_search_name('cai'), 'Units')
        self.assertEqual(map_uom_search_name('unknown-xyz'), 'Units')

    def test_map_covers_common_portal_units(self):
        for code in ('met', 'cai', 'kg', 'cuon', 'bao'):
            self.assertIn(code, NPL_UOM_MAP)


class NplBuildValsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit, _ = Unit.objects.get_or_create(code='met', defaults={'name': 'Met'})
        cls.cat, _ = MaterialCategory.objects.get_or_create(
            code='vai-bridge-test',
            defaults={'name': 'Vai Bridge Test'},
        )
        cls.mat = Material.objects.create(
            code='TEST-NPL-BRIDGE-001',
            name='VAI TEST BRIDGE',
            category=cls.cat,
            unit=cls.unit,
            base_price=Decimal('45000'),
        )

    def test_build_material_vals(self):
        vals = build_material_vals(self.mat, categ_id=10, uom_id=5)
        self.assertEqual(vals['default_code'], 'TEST-NPL-BRIDGE-001')
        self.assertEqual(vals['type'], 'consu')
        self.assertTrue(vals['is_storable'])
        self.assertFalse(vals['sale_ok'])
        self.assertTrue(vals['purchase_ok'])
        self.assertEqual(vals['categ_id'], 10)
        self.assertEqual(vals['uom_id'], 5)
        self.assertEqual(vals['uom_po_id'], 5)
        self.assertEqual(vals['standard_price'], 45000.0)

    def test_constants(self):
        self.assertEqual(NPL_CATEGORY_ROOT, 'Kho NPL')
        self.assertEqual(NPL_WAREHOUSE_CODE, 'NPL')


class NplPushDryRunMockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        unit, _ = Unit.objects.get_or_create(code='cai', defaults={'name': 'Cai'})
        cat, _ = MaterialCategory.objects.get_or_create(
            code='tem-bridge-test',
            defaults={'name': 'Tem Bridge Test'},
        )
        Material.objects.create(
            code='TEST-NPL-DRY-001',
            name='TEM TEST',
            category=cat,
            unit=unit,
            base_price=Decimal('1000'),
        )

    @patch('kho_npl.odoo_bridge.push_npl_stock')
    @patch('kho_npl.odoo_bridge.ensure_npl_suppliers')
    @patch('kho_npl.odoo_bridge.ensure_npl_locations')
    @patch('kho_npl.odoo_bridge.ensure_npl_warehouse')
    @patch('kho_npl.odoo_bridge.ensure_npl_category_tree')
    @patch('kho_npl.odoo_bridge.fetch_odoo_products_by_code')
    def test_push_dry_run_counts_create(
        self,
        mock_fetch,
        mock_cat,
        mock_wh,
        mock_loc,
        mock_sup,
        mock_stock,
    ):
        from kho_npl.odoo_bridge import push_materials

        mock_cat.return_value = {'root_id': 1, 'cat_map': {}, 'created': ['Kho NPL']}
        mock_wh.return_value = {
            'warehouse_id': None,
            'stock_location_id': None,
            'scrap_location_id': None,
            'created': True,
            'name': 'Kho NPL',
        }
        mock_loc.return_value = {'map': {}, 'created': [], 'reused': []}
        mock_sup.return_value = {'map': {}, 'created': [], 'updated': []}
        mock_fetch.return_value = {}

        result = push_materials(
            dry_run=True,
            codes={'TEST-NPL-DRY-001'},
            with_stock=False,
        )
        self.assertTrue(result.dry_run)
        self.assertEqual(result.materials_total, 1)
        self.assertEqual(result.materials_created, 1)
        mock_stock.assert_not_called()
        mock_sup.assert_called_once()


class NplSupplierPartnerValsTests(TestCase):
    def test_partner_vals(self):
        from kho_npl.models import Supplier
        from kho_npl.odoo_bridge import _partner_vals_from_supplier

        sup = Supplier(code='NCC-TEST-01', name='NCC Test', phone='090', notes='x')
        vals = _partner_vals_from_supplier(sup)
        self.assertEqual(vals['ref'], 'NCC-TEST-01')
        self.assertEqual(vals['supplier_rank'], 1)
        self.assertEqual(vals['name'], 'NCC Test')
        self.assertEqual(vals['phone'], '090')

