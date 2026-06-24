from django.test import SimpleTestCase, TestCase

from equipment.models import Device
from equipment.services.device_mac import (
    extract_mac_from_description,
    resolve_device_mac,
)


class DeviceMacResolveTests(SimpleTestCase):
    def test_extract_mac_from_description(self):
        text = 'MAC chính: 58:04:4F:3F:FF:E9\nUser: x'
        self.assertEqual(extract_mac_from_description(text), '58:04:4F:3F:FF:E9')

    def test_prefers_ethernet_over_wifi_in_configuration(self):
        configuration = (
            'Mạng: VMware Network Adapter VMnet1=00:50:56:C0:00:01, '
            'Ethernet=30:56:0F:69:E8:76, Wi-Fi=58:04:4F:3F:FF:E9'
        )
        device = Device(configuration=configuration, description='MAC chính: 58:04:4F:3F:FF:E9')
        self.assertEqual(resolve_device_mac(device), '30:56:0F:69:E8:76')

    def test_linux_description_mac(self):
        description = 'MAC chính: 74:56:3C:D4:5D:75\nCard mạng: enp2s0:=1500,'
        device = Device(configuration='', description=description)
        self.assertEqual(resolve_device_mac(device), '74:56:3C:D4:5D:75')


class RustDeskMacFromScanTests(TestCase):
    def test_sync_copies_mac_from_device_scan_description(self):
        from audit.models import RustDeskHost
        from audit.services.rustdesk_device_sync import sync_host_from_device

        device = Device.objects.create(
            device_code='IT-MAC-001',
            name='DESKTOP-K68ACOR',
            category='PC',
            hostname='DESKTOP-K68ACOR',
            configuration=(
                'Mạng: VMware Network Adapter VMnet1=00:50:56:C0:00:01, '
                'Ethernet=30:56:0F:69:E8:76, Wi-Fi=58:04:4F:3F:FF:E9'
            ),
            description='MAC chính: 58:04:4F:3F:FF:E9',
        )
        host = RustDeskHost.objects.create(
            name='DESKTOP-K68ACOR',
            hostname='DESKTOP-K68ACOR',
            rustdesk_id='123456789',
            device=device,
        )
        _, mac_updated = sync_host_from_device(host, save=True)
        host.refresh_from_db()
        device.refresh_from_db()
        self.assertTrue(mac_updated)
        self.assertEqual(host.mac_address, '30:56:0F:69:E8:76')
        self.assertEqual(device.mac_address, '30:56:0F:69:E8:76')
        self.assertEqual(host.effective_mac_address, '30:56:0F:69:E8:76')
