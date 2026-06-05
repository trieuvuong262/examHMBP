"""Tests đường dẫn nhóm hàng đầy đủ."""

from django.test import TestCase, override_settings

from kiotviet.category_paths import CategoryPathResolver, PATH_SEP
from kiotviet.formatters import format_product_group_row
from kiotviet.product_groups import browse_product_groups
from kiotviet.sync_service import upsert_category, upsert_product


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_CLIENT_ID='x',
    KIOTVIET_CLIENT_SECRET='y',
    KIOTVIET_USE_LOCAL_MIRROR=True,
)
class CategoryPathTests(TestCase):
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
        upsert_category(self.retailer, {
            'id': 111,
            'categoryName': 'Serie A',
            'parentId': 110,
            'modifiedDate': '2024-01-01T08:00:00',
        })

    def test_resolve_three_level_path(self):
        resolver = CategoryPathResolver(self.retailer)
        info = resolver.resolve(111)
        self.assertEqual(
            info['category_path'],
            f'Quần áo{PATH_SEP}Áo đấu{PATH_SEP}Serie A',
        )
        self.assertEqual(info['category_path_parts'], ['Quần áo', 'Áo đấu', 'Serie A'])
        self.assertEqual(info['category_name'], 'Serie A')

    def test_product_group_uses_full_category_path(self):
        upsert_product(self.retailer, {
            'id': 5001,
            'code': 'SP05001',
            'name': 'AC Milan home 25-26',
            'categoryId': 111,
            'categoryName': 'Serie A',
            'isActive': True,
            'basePrice': 350000,
            'modifiedDate': '2024-03-01T08:00:00',
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 3}],
        })
        from kiotviet.product_filters import ProductListFilters
        filters = ProductListFilters(is_active='')
        groups, total = browse_product_groups(
            page=1, per_page=30, retailer=self.retailer, filters=filters,
        )
        self.assertEqual(total, 1)
        row = format_product_group_row(groups[0])
        self.assertEqual(row['category_path_parts'], ['Quần áo', 'Áo đấu', 'Serie A'])
        self.assertIn('Quần áo', row['category_path'])
        self.assertIn('Serie A', row['category_path'])
        self.assertEqual(groups[0].category_kiotviet_id, 111)

    def test_fallback_when_category_missing_in_mirror(self):
        resolver = CategoryPathResolver(self.retailer)
        info = resolver.resolve(99999, fallback_name='Nhóm lẻ')
        self.assertEqual(info['category_path'], 'Nhóm lẻ')
        self.assertEqual(info['category_name'], 'Nhóm lẻ')
