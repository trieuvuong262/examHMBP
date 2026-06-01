from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from equipment.services.email_notify import get_it_notify_emails
from equipment.services.wmi_scan import is_bad_serial as scan_bad_serial, parse_ip_range


class WmiScanHelpersTests(SimpleTestCase):
    def test_is_bad_serial(self):
        self.assertTrue(scan_bad_serial('Default string'))
        self.assertTrue(scan_bad_serial(None))
        self.assertFalse(scan_bad_serial('ABC123456'))

    def test_parse_ip_range(self):
        ips = parse_ip_range('192.168.1.1', '192.168.1.3')
        self.assertEqual(ips, ['192.168.1.1', '192.168.1.2', '192.168.1.3'])

    def test_parse_ip_range_too_large(self):
        with self.assertRaises(ValueError):
            parse_ip_range('10.0.0.0', '10.0.2.0')

    @override_settings(DEBUG=True)
    def test_wmi_supported_on_windows_debug(self):
        from unittest.mock import patch
        from equipment.services.wmi_scan import is_wmi_scan_supported

        with patch('equipment.services.wmi_scan.platform.system', return_value='Windows'):
            self.assertTrue(is_wmi_scan_supported())

    @override_settings(DEBUG=True)
    def test_wmi_not_supported_on_linux(self):
        from unittest.mock import patch
        from equipment.services.wmi_scan import is_wmi_scan_supported

        with patch('equipment.services.wmi_scan.platform.system', return_value='Linux'):
            self.assertFalse(is_wmi_scan_supported())


class EmailNotifyTests(SimpleTestCase):
    @override_settings(EQUIPMENT_NOTIFY_EMAILS='a@test.com,b@test.com')
    def test_get_it_notify_emails_from_env(self):
        with patch('service_requests.workflow_it.get_it_department', return_value=None):
            emails = get_it_notify_emails()
        self.assertEqual(emails, ['a@test.com', 'b@test.com'])
