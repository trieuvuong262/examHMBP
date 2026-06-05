"""Tests bộ lọc danh sách hàng hoá."""

from django.test import TestCase, override_settings

from kiotviet.product_filters import (
    ProductListFilters,
    category_descendant_ids,
    filter_product_groups,
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
            'basePrice': 200000,
            'modifiedDate': '2024-03-01T08:00:00',
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 0}],
        })

    def test_category_descendant_ids(self):
        ids = category_descendant_ids(self.retailer, 100)
        self.assertEqual(ids, {100, 110})

    def test_filter_by_parent_category(self):
        filters = ProductListFilters(category_id=100)
        groups, total = browse_product_groups(
            page=1, per_page=30, retailer=self.retailer, filters=filters,
        )
        self.assertEqual(total, 2)

    def test_filter_stock_and_allows_sale(self):
        filters = ProductListFilters(stock='yes', allows_sale='yes')
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

    def test_parse_product_filters_from_request(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(
            '/kiotviet/hang-hoa/?category=110&allows_sale=yes&is_active=no&stock=yes',
        )
        parsed = parse_product_filters(request)
        self.assertEqual(parsed.category_id, 110)
        self.assertEqual(parsed.allows_sale, 'yes')
        self.assertEqual(parsed.is_active, 'no')
        self.assertEqual(parsed.stock, 'yes')
        self.assertTrue(parsed.is_active_filter())
