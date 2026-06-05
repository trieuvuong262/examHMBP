from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from kiotviet.models import (
    KvCustomerGroup,
    KvProduct,
    KvPurchaseOrder,
    KvPurchaseOrderLine,
    KvReturn,
    KvReturnLine,
    KvTransfer,
    KvTransferLine,
)
from kiotviet.sync_service import (
    ENTITY_ALL,
    ENTITY_SYNC_OPTIONS,
    refresh_product_images,
    sync_entity,
    upsert_customer_group,
    upsert_purchase_order,
    upsert_return,
    upsert_transfer,
)


@override_settings(KIOTVIET_RETAILER='justsport')
class PurchaseOrderSyncTests(TestCase):
    retailer = 'justsport'

    def test_upsert_purchase_order_uses_purchase_date_when_no_modified(self):
        upsert_purchase_order(self.retailer, {
            'id': 9001,
            'code': 'PN001',
            'purchaseDate': '2024-06-15T08:30:00',
            'status': 1,
            'statusValue': 'Hoàn thành',
            'purchaseOrderDetails': [{
                'productId': 101,
                'productCode': 'SP-X',
                'productName': 'Hang A',
                'quantity': 2,
                'price': 100000,
            }],
        })
        po = KvPurchaseOrder.objects.get(kiotviet_id=9001)
        self.assertIsNotNone(po.kv_modified_at)
        self.assertEqual(po.purchase_date.year, 2024)
        self.assertEqual(KvPurchaseOrderLine.objects.filter(purchase_order_kiotviet_id=9001).count(), 1)

    @patch('kiotviet.sync_service.KiotVietClient')
    def test_sync_purchase_orders_omits_modified_api_params(self, mock_client_cls):
        mock_api = MagicMock()
        mock_client_cls.return_value = mock_api
        mock_api.list_purchase_orders.return_value = {
            'data': [],
            'total': 0,
            'removedIds': [],
        }

        result = sync_entity('purchase_orders', client=mock_api, retailer=self.retailer)

        self.assertIsNone(result.get('error'))
        params = mock_api.list_purchase_orders.call_args.kwargs
        self.assertNotIn('lastModifiedFrom', params)
        self.assertNotIn('includeRemoveIds', params)
        self.assertNotIn('orderBy', params)

    def test_purchase_orders_entity_options(self):
        opts = ENTITY_SYNC_OPTIONS['purchase_orders']
        self.assertFalse(opts.supports_last_modified)
        self.assertFalse(opts.supports_remove_ids)


@override_settings(KIOTVIET_RETAILER='justsport')
class ProductImageRefreshTests(TestCase):
    retailer = 'justsport'

    def test_refresh_product_images_backfills_missing_urls(self):
        KvProduct.objects.create(
            retailer='justsport',
            kiotviet_id=5001,
            code='IMG-A',
            name='Ao',
            image_urls=[],
        )

        mock_api = MagicMock()
        mock_api.list_purchase_orders = MagicMock()
        mock_api.list_products.return_value = {
            'data': [{
                'id': 5001,
                'code': 'IMG-A',
                'name': 'Ao',
                'modifiedDate': '2024-01-01T00:00:00',
                'images': [{'Image': 'https://cdn.example/img.jpg'}],
            }],
            'total': 1,
            'removedIds': [],
        }

        result = refresh_product_images(client=mock_api, retailer=self.retailer)

        self.assertIsNone(result.get('error'))
        self.assertEqual(result.get('upserted'), 1)
        product = KvProduct.objects.get(kiotviet_id=5001)
        self.assertEqual(product.image_urls, ['https://cdn.example/img.jpg'])

    def test_refresh_skips_when_images_already_set(self):
        KvProduct.objects.create(
            retailer='justsport',
            kiotviet_id=5002,
            code='IMG-B',
            name='Quan',
            image_urls=['https://cdn.example/existing.jpg'],
        )

        mock_api = MagicMock()
        mock_api.list_products.return_value = {
            'data': [{
                'id': 5002,
                'images': [{'Image': 'https://cdn.example/new.jpg'}],
            }],
            'total': 1,
            'removedIds': [],
        }

        result = refresh_product_images(client=mock_api, retailer=self.retailer)

        self.assertEqual(result.get('skipped'), 1)
        product = KvProduct.objects.get(kiotviet_id=5002)
        self.assertEqual(product.image_urls, ['https://cdn.example/existing.jpg'])


@override_settings(KIOTVIET_RETAILER='justsport')
class ExtendedEntitySyncTests(TestCase):
    retailer = 'justsport'

    def test_entity_all_includes_extended_entities(self):
        self.assertIn('transfers', ENTITY_ALL)
        self.assertIn('returns', ENTITY_ALL)
        self.assertIn('customer_groups', ENTITY_ALL)
        self.assertIn('cashflow', ENTITY_ALL)

    def test_upsert_transfer_with_lines(self):
        upsert_transfer(self.retailer, {
            'id': 7001,
            'code': 'CK001',
            'fromBranchId': 1,
            'toBranchId': 2,
            'status': 1,
            'dispatchedDate': '2024-08-01T10:00:00',
            'transferDetails': [{
                'productId': 101,
                'ProductCode': 'SP-A',
                'sendQuantity': 5,
                'price': 100000,
            }],
        })
        transfer = KvTransfer.objects.get(kiotviet_id=7001)
        self.assertEqual(transfer.code, 'CK001')
        self.assertEqual(KvTransferLine.objects.filter(transfer_kiotviet_id=7001).count(), 1)

    def test_upsert_customer_group(self):
        upsert_customer_group(self.retailer, {
            'id': 8001,
            'name': 'Khách sỉ',
            'description': 'Nhóm sỉ',
            'discountRatio': 5,
            'createdDate': '2024-01-01T00:00:00',
        })
        group = KvCustomerGroup.objects.get(kiotviet_id=8001)
        self.assertEqual(group.name, 'Khách sỉ')
        self.assertEqual(group.discount_ratio, 5.0)

    def test_upsert_return_without_discount_on_line(self):
        upsert_return(self.retailer, {
            'id': 9002,
            'code': 'TH001',
            'returnDate': '2024-09-01T12:00:00',
            'modifiedDate': '2024-09-01T12:00:00',
            'returnDetails': [{
                'productId': 201,
                'productCode': 'SP-B',
                'productName': 'Quan',
                'quantity': 1,
                'price': 200000,
                'discount': 10000,
                'note': 'Doi size',
            }],
        })
        self.assertEqual(KvReturn.objects.get(kiotviet_id=9002).code, 'TH001')
        line = KvReturnLine.objects.get(return_kiotviet_id=9002)
        self.assertEqual(line.note, 'Doi size')
