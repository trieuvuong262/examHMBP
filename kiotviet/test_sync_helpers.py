from django.test import TestCase, override_settings

from kiotviet.models import KvProduct
from kiotviet.sync_helpers import extract_product_image_urls, needs_upsert
from kiotviet.sync_service import upsert_product


@override_settings(KIOTVIET_RETAILER='justsport')
class SyncHelpersTests(TestCase):
    retailer = 'justsport'

    def test_extract_product_image_urls(self):
        urls = extract_product_image_urls({
            'images': [
                {'Image': 'https://cdn.example/a.jpg'},
                'https://cdn.example/b.jpg',
            ],
        })
        self.assertEqual(urls, [
            'https://cdn.example/a.jpg',
            'https://cdn.example/b.jpg',
        ])

    def test_skip_unchanged_product(self):
        upsert_product(self.retailer, {
            'id': 3001,
            'code': 'SP-A',
            'name': 'Ao',
            'modifiedDate': '2024-03-01T10:00:00',
            'images': [{'Image': 'https://cdn.example/sp.jpg'}],
        })
        self.assertFalse(upsert_product(self.retailer, {
            'id': 3001,
            'code': 'SP-A',
            'name': 'Ao',
            'modifiedDate': '2024-03-01T10:00:00',
        }))
        product = KvProduct.objects.get(kiotviet_id=3001)
        self.assertEqual(product.image_urls, ['https://cdn.example/sp.jpg'])

    def test_needs_upsert_for_new_record(self):
        self.assertTrue(
            needs_upsert(KvProduct, retailer=self.retailer, kiotviet_id=9999, incoming_modified=None)
        )
