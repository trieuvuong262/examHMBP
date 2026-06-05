"""Tests gộp sản phẩm quần áo theo tên (nhiều size = nhiều mã)."""

from django.test import TestCase, override_settings

from kiotviet.models import KvProduct, KvProductAttribute, KvProductInventory
from kiotviet.formatters import format_product_group_detail, format_product_group_row
from kiotviet.product_filters import ProductListFilters
from kiotviet.product_groups import browse_product_groups, get_product_group
from kiotviet.sync_service import upsert_product


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_CLIENT_ID='x',
    KIOTVIET_CLIENT_SECRET='y',
    KIOTVIET_USE_LOCAL_MIRROR=True,
)
class ProductGroupTests(TestCase):
    retailer = 'justsport'
    style_name = 'AC Milan đỏ sọc đen sân nhà 25-26'

    def _upsert_size(self, kid: int, code: str, size: str, on_hand: float) -> None:
        upsert_product(self.retailer, {
            'id': kid,
            'code': code,
            'name': self.style_name,
            'isActive': True,
            'basePrice': 350000,
            'modifiedDate': '2024-03-01T08:00:00',
            'attributes': [{
                'attributeName': 'Size',
                'attributeValue': size,
            }],
            'inventories': [{
                'branchId': 1,
                'branchName': 'Chi nhánh 1',
                'onHand': on_hand,
                'reserved': 0,
            }],
        })

    def test_browse_groups_apparel_sizes(self):
        self._upsert_size(7624, 'SP007624', 'S', 2)
        self._upsert_size(7625, 'SP007625', 'M', 5)
        self._upsert_size(7626, 'SP007626', 'L', 3)

        groups, total = browse_product_groups(page=1, per_page=30, retailer=self.retailer)
        self.assertEqual(total, 1)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.name, self.style_name)
        self.assertEqual(group.variant_count, 3)
        self.assertEqual(group.total_on_hand, 10.0)
        self.assertEqual(set(group.codes), {'SP007624', 'SP007625', 'SP007626'})

    def test_lookup_by_code_returns_whole_group(self):
        self._upsert_size(7624, 'SP007624', 'S', 1)
        self._upsert_size(7625, 'SP007625', 'M', 2)

        groups, total = browse_product_groups(
            page=1, per_page=30, code='SP007625', retailer=self.retailer,
        )
        self.assertEqual(total, 1)
        self.assertEqual(groups[0].variant_count, 2)
        self.assertEqual(groups[0].total_on_hand, 3.0)

    def test_detail_shows_variants(self):
        self._upsert_size(7624, 'SP007624', 'S', 4)
        self._upsert_size(7625, 'SP007625', 'M', 6)

        detail = get_product_group(self.retailer, 7625)
        self.assertIsNotNone(detail)
        self.assertEqual(detail['variant_count'], 2)
        self.assertEqual(detail['total_on_hand'], 10.0)
        codes = {v['code'] for v in detail['variants']}
        self.assertEqual(codes, {'SP007624', 'SP007625'})
        sizes = {v['size_label'] for v in detail['variants']}
        self.assertEqual(sizes, {'S', 'M'})

    def test_detail_includes_statuses(self):
        upsert_product(self.retailer, {
            'id': 7624,
            'code': 'SP007624',
            'name': self.style_name,
            'allowsSale': True,
            'isActive': True,
            'hasVariants': True,
            'productType': 2,
            'basePrice': 350000,
            'modifiedDate': '2024-03-01T08:00:00',
            'attributes': [{'attributeName': 'Size', 'attributeValue': 'S'}],
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 1}],
        })
        formatted = format_product_group_detail(get_product_group(self.retailer, 7624))
        self.assertEqual(formatted['allows_sale_status']['label'], 'Có')
        self.assertEqual(formatted['is_active_status']['label'], 'Có')
        self.assertEqual(formatted['product_type_label'], 'Hàng thường')
        self.assertEqual(formatted['variants'][0]['allows_sale_status']['label'], 'Có')

    def test_stock_matrix_groups_by_branch_and_size(self):
        self._upsert_size(7624, 'SP007624', 'S', 2)
        self._upsert_size(7625, 'SP007625', 'M', 5)
        formatted = format_product_group_detail(get_product_group(self.retailer, 7624))
        matrix = formatted['stock_matrix']
        self.assertTrue(matrix['show_size_columns'])
        self.assertEqual(len(matrix['columns']), 2)
        self.assertEqual(matrix['rows'][0]['on_hand'], 7.0)

    def test_list_row_includes_statuses(self):
        upsert_product(self.retailer, {
            'id': 7624,
            'code': 'SP007624',
            'name': self.style_name,
            'allowsSale': True,
            'isActive': False,
            'basePrice': 350000,
            'modifiedDate': '2024-03-01T08:00:00',
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 1}],
        })
        groups, _ = browse_product_groups(
            page=1, per_page=30, retailer=self.retailer,
            filters=ProductListFilters(is_active='no'),
        )
        row = format_product_group_row(groups[0])
        self.assertEqual(row['allows_sale_status']['label'], 'Có')
        self.assertEqual(row['is_active_status']['label'], 'Không')

    def test_single_product_stays_one_group(self):
        upsert_product(self.retailer, {
            'id': 9001,
            'code': 'BONG01',
            'name': 'Bóng đá size 5',
            'isActive': True,
            'basePrice': 120000,
            'modifiedDate': '2024-03-01T08:00:00',
            'inventories': [{'branchId': 1, 'branchName': 'CN1', 'onHand': 7}],
        })
        groups, total = browse_product_groups(page=1, per_page=30, retailer=self.retailer)
        self.assertEqual(total, 1)
        self.assertEqual(groups[0].variant_count, 1)
        self.assertEqual(groups[0].total_on_hand, 7.0)
