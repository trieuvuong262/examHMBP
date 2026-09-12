"""Tests dong bo KiotViet: clip varchar, lich 6h/12h/19h, khach hang so dai."""

from django.test import SimpleTestCase, TestCase

from kiotviet.models import KvCustomer
from kiotviet.sync_helpers import (
    CRON_THRICE_DAILY,
    DEFAULT_SYNC_INTERVAL_MINUTES,
    SYNC_INTERVAL_THRICE_DAILY,
    clip_charfield_defaults,
    clip_text,
    cron_hint_for_minutes,
    normalize_interval_minutes,
)
from kiotviet.sync_service import ENTITY_ALL, upsert_customer


class SyncHelperTests(SimpleTestCase):
    def test_thrice_daily_cron_hint(self):
        self.assertEqual(cron_hint_for_minutes(SYNC_INTERVAL_THRICE_DAILY), CRON_THRICE_DAILY)
        self.assertEqual(CRON_THRICE_DAILY, '0 6,12,19 * * *')

    def test_thrice_daily_not_confused_with_12h_interval(self):
        self.assertEqual(cron_hint_for_minutes(720), '0 */12 * * *')
        self.assertNotEqual(cron_hint_for_minutes(481), cron_hint_for_minutes(720))

    def test_normalize_thrice_daily_default(self):
        self.assertEqual(normalize_interval_minutes(None), DEFAULT_SYNC_INTERVAL_MINUTES)
        self.assertEqual(normalize_interval_minutes('481'), SYNC_INTERVAL_THRICE_DAILY)
        self.assertEqual(normalize_interval_minutes('99'), DEFAULT_SYNC_INTERVAL_MINUTES)

    def test_clip_text(self):
        self.assertEqual(clip_text(None, 5), '')
        self.assertEqual(clip_text('abcde', 5), 'abcde')
        self.assertEqual(clip_text('abcdef', 5), 'abcde')
        self.assertEqual(clip_text(1234567890, 4), '1234')

    def test_clip_charfield_defaults_uses_model_max_length(self):
        long_phone = '0901 234 567 / 0912 345 678 / 028 1234 5678 extra'
        clipped = clip_charfield_defaults(
            KvCustomer,
            {'contact_number': long_phone, 'tax_code': '1' * 80, 'name': 'KH Test'},
        )
        self.assertLessEqual(len(clipped['contact_number']), KvCustomer._meta.get_field('contact_number').max_length)
        self.assertLessEqual(len(clipped['tax_code']), KvCustomer._meta.get_field('tax_code').max_length)
        self.assertTrue(clipped['contact_number'].startswith('0901'))
        self.assertEqual(clipped['name'], 'KH Test')


class UpsertCustomerLengthTests(TestCase):
    def test_long_contact_number_and_tax_code_are_saved(self):
        long_phone = '0901234567 / 0912345678 / 02812345678 / 0934567890'
        long_tax = '0' * 80
        ok = upsert_customer(
            'justsport',
            {
                'id': 99000001,
                'code': 'KHCLIP',
                'name': 'Khach hang so dai',
                'contactNumber': long_phone,
                'taxCode': long_tax,
            },
            force=True,
        )
        self.assertTrue(ok)
        obj = KvCustomer.objects.get(retailer='justsport', kiotviet_id=99000001)
        max_phone = KvCustomer._meta.get_field('contact_number').max_length
        max_tax = KvCustomer._meta.get_field('tax_code').max_length
        self.assertLessEqual(len(obj.contact_number), max_phone)
        self.assertLessEqual(len(obj.tax_code), max_tax)
        self.assertEqual(obj.contact_number, long_phone[:max_phone])
        self.assertEqual(obj.tax_code, long_tax[:max_tax])
        self.assertGreater(len(long_phone), 32)

    def test_entity_all_covers_customers(self):
        self.assertIn('customers', ENTITY_ALL)
        self.assertGreaterEqual(len(ENTITY_ALL), 10)
