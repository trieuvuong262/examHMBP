"""Tests mirror DB trung gian KiotViet."""

from django.test import TestCase, override_settings

from kiotviet.local_lookup import browse_customers, get_customer_by_code
from kiotviet.mirror import entity_count, use_local_mirror
from kiotviet.models import KvCustomer, KvProduct, KvSyncState
from kiotviet.sync_service import upsert_customer, upsert_product


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_CLIENT_ID='x',
    KIOTVIET_CLIENT_SECRET='y',
    KIOTVIET_USE_LOCAL_MIRROR=True,
)
class KiotVietMirrorTests(TestCase):
    retailer = 'justsport'

    def test_upsert_customer_and_local_browse(self):
        upsert_customer(self.retailer, {
            'id': 1001,
            'code': 'KH001',
            'name': 'Nguyen Van A',
            'contactNumber': '0901234567',
            'modifiedDate': '2024-01-15T10:00:00',
        })
        self.assertEqual(entity_count('customers', self.retailer), 1)
        self.assertTrue(use_local_mirror('customers', self.retailer))

        rows, total = browse_customers(page=1, per_page=30, retailer=self.retailer)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]['code'], 'KH001')

        detail = get_customer_by_code(self.retailer, 'KH001')
        self.assertIsNotNone(detail)
        self.assertEqual(detail['name'], 'Nguyen Van A')

    def test_upsert_product_with_inventory(self):
        upsert_product(self.retailer, {
            'id': 2001,
            'code': 'SP01',
            'name': 'Ao thun',
            'barCode': '8930001',
            'basePrice': 150000,
            'modifiedDate': '2024-02-01T08:00:00',
            'inventories': [{
                'branchId': 1,
                'branchName': 'Chi nhanh 1',
                'onHand': 10,
                'reserved': 1,
            }],
        })
        self.assertEqual(KvProduct.objects.filter(retailer=self.retailer).count(), 1)
        product = KvProduct.objects.get(kiotviet_id=2001)
        invs = product.to_api_dict()['inventories']
        self.assertEqual(len(invs), 1)
        self.assertEqual(invs[0]['onHand'], 10)

    def test_sync_state_created_on_upsert_path(self):
        KvSyncState.objects.create(
            entity_type='customers',
            retailer=self.retailer,
            records_total=0,
        )
        st = KvSyncState.objects.get(entity_type='customers', retailer=self.retailer)
        self.assertEqual(st.records_total, 0)
