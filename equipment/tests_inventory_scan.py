import io
import json
import zipfile

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from equipment.models import Device
from equipment.services.inventory_scan import normalize_mac
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
from hrm.permissions import ROLE_EMPLOYEE
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_DOCUMENTS


class EquipmentInventoryScanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT Scan', sort_order=1)
        DepartmentMenuPermission.objects.create(department=cls.dept, modules=['documents'])
        perms = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        perms[MODULE_DOCUMENTS] = {
            'view': True,
            'menus': {
                'equipment_scan': {
                    'view': True,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                },
            },
        }
        cls.group = PermissionGroup.objects.create(
            slug='test-equipment-scan',
            name='Equipment scan',
            module_permissions=perms,
        )
        cls.user = User.objects.create_user('eqscan', password='x')
        profile = Profile.objects.get(user=cls.user)
        profile.department = cls.dept
        profile.full_name = 'Nhan Vien Quet'
        profile.role = ROLE_EMPLOYEE
        profile.permission_group = cls.group
        profile.save()

    def setUp(self):
        self.client = Client(HTTP_HOST='testserver')

    def test_normalize_mac(self):
        self.assertEqual(normalize_mac('aabbccddeeff'), 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(normalize_mac('AA-BB-CC-DD-EE-FF'), 'AA:BB:CC:DD:EE:FF')

    @override_settings(EQUIPMENT_SCAN_SECRET='scan-secret')
    def test_check_api_reports_existing_mac(self):
        Device.objects.create(
            device_code='TB-000099',
            name='PC-OLD',
            category='PC',
            mac_address='11:22:33:44:55:66',
        )
        resp = self.client.post(
            reverse('equipment:equipment_scan_check_api'),
            data=json.dumps({
                'scan_secret': 'scan-secret',
                'mac_address': '11:22:33:44:55:66',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['exists'])
        self.assertEqual(data['device_code'], 'TB-000099')

    @override_settings(EQUIPMENT_SCAN_SECRET='scan-secret')
    def test_submit_creates_device_once(self):
        payload = {
            'scan_secret': 'scan-secret',
            'mac_address': 'AA:BB:CC:DD:EE:01',
            'hostname': 'PC-NEW',
            'ip_address': '10.1.2.3',
            'manufacturer': 'Dell Inc.',
            'model': 'OptiPlex 7090',
            'cpu': 'Intel Core i5',
            'ram_gb': '16',
            'os_name': 'Windows 11 Pro',
            'assigned_user_text': 'Test User',
            'department_text': 'IT Scan',
        }
        resp = self.client.post(
            reverse('equipment:equipment_scan_submit_api'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['created'])
        device = Device.objects.get(mac_address='AA:BB:CC:DD:EE:01')
        self.assertEqual(device.hostname, 'PC-NEW')
        self.assertEqual(device.assigned_user_text, 'Test User')
        self.assertIn('Intel Core i5', device.configuration)

        resp2 = self.client.post(
            reverse('equipment:equipment_scan_submit_api'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp2.json()['status'], 'skipped')
        self.assertEqual(Device.objects.filter(mac_address='AA:BB:CC:DD:EE:01').count(), 1)

    @override_settings(EQUIPMENT_SCAN_SECRET='scan-secret')
    def test_windows_download_embeds_downloader_name(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('documents:equipment_scan_download') + '?os=win')
        self.assertEqual(resp.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            ps1 = archive.read('JustPlay-Equipment-Scan.ps1').decode('utf-8-sig')
        self.assertIn('scan-secret', ps1)
        self.assertIn('Nhan Vien Quet', ps1)
        self.assertIn('IT Scan', ps1)

    @override_settings(EQUIPMENT_SCAN_SECRET='scan-secret')
    def test_scan_config_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('documents:equipment_scan_config'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Quét cấu hình thiết bị IT')
        self.assertContains(resp, reverse('documents:equipment_scan_download') + '?os=win')
