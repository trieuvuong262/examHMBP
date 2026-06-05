"""Tests bộ lọc danh sách hàng hoá."""

from django.test import RequestFactory, TestCase, override_settings

from kiotviet.product_filters import (
    DEFAULT_IS_ACTIVE,
    ProductListFilters,
    category_descendant_ids,
    parse_product_filters,
)
from kiotviet.product_groups import browse_product_groups
from kiotviet.sync_service import upsert_category, upsert_product


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_CLIENT_ID='x',
    KIOTVIET_CLIENT_SECRET='y',
    KIOTVIET_USE_LOCAL_MIRROR=True,
)
class ProductFilterTests(TestCase):
    retailer = 'justsport'

    def setUp(self):
        upsert_category(self.retailer, {
            'id': 100,
            'categoryName': 'Quần áo',
            'parentId': None,
            'modifiedDate': '2024-01-01T08:00:00',
        })
        upsert_category(self.retailer, {
            'id': 110,
            'categoryName': 'Áo đấu',
            'parentId': 100,
            'modifiedDate': '2024-01-01T08:00:00',
        })
        upsert_product(self.retailer, {
            'id': 1,
            'code': 'SP001',
            'name': 'SP A',
            'categoryId': 110,
            'categoryName': 'Áo đấu',
            'allowsSale': True,
            'isActive': True,
            'productType': 2,
            'unit': 'Cái',
            'basePrice': 100000,
            'modifiedDate': '2024-03-01T08:00:00',
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 5}],
        })
        upsert_product(self.retailer, {
            'id': 2,
            'code': 'SP002',
            'name': 'SP B',
            'categoryId': 100,
            'categoryName': 'Quần áo',
            'allowsSale': False,
            'isActive': False,
            'productType': 2,
            'unit': 'Bộ',
            'basePrice': 200000,
            'modifiedDate': '2024-03-01T08:00:00',
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 0}],
        })

    def test_category_descendant_ids(self):
        ids = category_descendant_ids(self.retailer, 100)
        self.assertEqual(ids, {100, 110})

    def test_default_only_active_products(self):
        groups, total = browse_product_groups(page=1, per_page=30, retailer=self.retailer)
        self.assertEqual(total, 1)
        self.assertEqual(groups[0].codes, ['SP001'])

    def test_filter_by_parent_category(self):
        filters = ProductListFilters(category_id=100, is_active='')
        groups, total = browse_product_groups(
            page=1, per_page=30, retailer=self.retailer, filters=filters,
        )
        self.assertEqual(total, 2)

    def test_filter_stock_on_active_products(self):
        filters = ProductListFilters(stock='yes')
        groups, total = browse_product_groups(
            page=1, per_page=30, retailer=self.retailer, filters=filters,
        )
        self.assertEqual(total, 1)
        self.assertEqual(groups[0].codes, ['SP001'])

    def test_filters_without_keyword(self):
        filters = ProductListFilters(is_active='no')
        groups, total = browse_product_groups(
            page=1, per_page=30, retailer=self.retailer, filters=filters,
        )
        self.assertEqual(total, 1)
        self.assertEqual(groups[0].codes, ['SP002'])

    def test_category_path_saved_on_upsert(self):
        from kiotviet.models import KvProduct
        product = KvProduct.objects.get(kiotviet_id=1)
        self.assertIn('Quần áo', product.category_path)
        self.assertIn('Áo đấu', product.category_path)

    def test_parse_product_filters_default_active(self):
        factory = RequestFactory()
        request = factory.get('/kiotviet/hang-hoa/')
        parsed = parse_product_filters(request)
        self.assertEqual(parsed.is_active, DEFAULT_IS_ACTIVE)
        self.assertFalse(parsed.is_non_default_filter())

    def test_parse_product_filters_from_request(self):
        factory = RequestFactory()
        request = factory.get(
            '/kiotviet/hang-hoa/?category=110&is_active=all&stock=yes&product_type=2&unit=Cái&sort=stock_desc&category_q=ao',
        )
        parsed = parse_product_filters(request)
        self.assertEqual(parsed.category_id, 110)
        self.assertEqual(parsed.is_active, '')
        self.assertEqual(parsed.stock, 'yes')
        self.assertEqual(parsed.product_type, '2')
        self.assertEqual(parsed.unit, 'Cái')
        self.assertEqual(parsed.sort, 'stock_desc')
        self.assertEqual(parsed.category_q, 'ao')
        self.assertTrue(parsed.is_non_default_filter())
