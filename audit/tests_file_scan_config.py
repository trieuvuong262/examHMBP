"""Test công tắc quét virus file trên màn hình Bảo mật đăng nhập."""

from __future__ import annotations

import socket
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audit import file_scan_config as fsc
from audit.models import FileScanConfig
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_AUDIT

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 40


class ConfigDefaultsTests(TestCase):
    def test_get_solo_seeds_from_env(self):
        """Lần đầu tạo phải lấy giá trị .env để không đổi hành vi đang chạy."""
        FileScanConfig.objects.all().delete()
        with override_settings(AV_SCAN_ENABLED=True, AV_FAIL_CLOSED=True):
            config = FileScanConfig.get_solo()
        self.assertTrue(config.enabled)
        self.assertTrue(config.fail_closed)

    def test_get_solo_is_singleton(self):
        a = FileScanConfig.get_solo()
        b = FileScanConfig.get_solo()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(FileScanConfig.objects.count(), 1)

    def test_db_overrides_env(self):
        fsc.save_config(enabled=True, fail_closed=False, admin_user=None)
        with override_settings(AV_SCAN_ENABLED=False):
            self.assertTrue(fsc.scan_enabled())

        fsc.save_config(enabled=False, fail_closed=False, admin_user=None)
        with override_settings(AV_SCAN_ENABLED=True):
            self.assertFalse(fsc.scan_enabled())

    @override_settings(AV_SCAN_FORCE_OFF=True)
    def test_force_off_beats_db(self):
        """Cầu dao trong .env phải thắng cấu hình DB."""
        fsc.save_config(enabled=True, fail_closed=False, admin_user=None)
        self.assertFalse(fsc.scan_enabled())

    def test_fail_closed_read_from_db(self):
        fsc.save_config(enabled=True, fail_closed=True, admin_user=None)
        with override_settings(AV_FAIL_CLOSED=False):
            self.assertTrue(fsc.scan_fail_closed())


class UploadGuardUsesSwitchTests(TestCase):
    """Công tắc phải thực sự điều khiển luồng upload."""

    def test_scanner_not_called_when_switch_off(self):
        from nas_storage.upload_guard import validate_upload

        fsc.save_config(enabled=False, fail_closed=False, admin_user=None)

        def boom(*_a, **_k):
            raise AssertionError('không được gọi scanner khi công tắc tắt')

        with patch.object(socket, 'create_connection', boom):
            validate_upload(SimpleUploadedFile('a.png', PNG))

    def test_scanner_called_when_switch_on(self):
        from nas_storage.upload_guard import UploadRejected, validate_upload

        fsc.save_config(enabled=True, fail_closed=False, admin_user=None)

        class FakeSock:
            def settimeout(self, _v): pass
            def sendall(self, _d): pass
            def recv(self, _n): return b'stream: Eicar-Test-Signature FOUND\0'
            def __enter__(self): return self
            def __exit__(self, *_e): return False

        with patch.object(socket, 'create_connection', lambda *a, **k: FakeSock()):
            with self.assertRaises(UploadRejected):
                validate_upload(SimpleUploadedFile('a.png', PNG))


class FileScanTabViewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='IT Scan', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['audit'])
        RoleModulePermission.objects.update_or_create(
            role='ADMIN',
            defaults={'module_permissions': {
                MODULE_AUDIT: {'view': True, 'edit': True, 'export': True},
            }},
        )
        self.user = User.objects.create_superuser(
            username='it_scan', email='a@b.c', password='x',
        )
        Profile.objects.filter(user=self.user).update(
            department=self.dept, role='ADMIN', full_name='IT Scan', is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_tab_button_present_on_other_tabs(self):
        resp = self.client.get(reverse('audit:login_security'), {'tab': 'config'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'tab=filescan')
        self.assertContains(resp, 'Quét virus file')

    def test_filescan_tab_renders(self):
        with patch('nas_storage.av_scan.ping', return_value=False):
            resp = self.client.get(reverse('audit:login_security'), {'tab': 'filescan'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Bật quét virus file tải lên')
        self.assertContains(resp, 'form-switch')

    def test_other_tabs_do_not_ping_scanner(self):
        """Ping clamd chỉ khi mở tab đó — không thêm I/O cho tab khác."""
        with patch('nas_storage.av_scan.ping', side_effect=AssertionError('không được ping')):
            self.assertEqual(
                self.client.get(reverse('audit:login_security'), {'tab': 'bots'}).status_code, 200,
            )
            self.assertEqual(
                self.client.get(reverse('audit:login_security'), {'tab': 'config'}).status_code, 200,
            )

    def test_switch_on_saves_and_warns_when_scanner_down(self):
        with patch('nas_storage.av_scan.ping', return_value=False):
            resp = self.client.post(
                reverse('audit:file_scan_save_config'),
                {'enabled': 'on'},
                follow=True,
            )
        self.assertTrue(FileScanConfig.get_solo().enabled)
        self.assertContains(resp, 'chưa liên lạc được ClamAV')

    def test_switch_on_success_when_scanner_alive(self):
        with patch('nas_storage.av_scan.ping', return_value=True), \
                patch('nas_storage.av_scan.version', return_value='ClamAV 1.4.1'):
            resp = self.client.post(
                reverse('audit:file_scan_save_config'),
                {'enabled': 'on', 'fail_closed': 'on'},
                follow=True,
            )
        config = FileScanConfig.get_solo()
        self.assertTrue(config.enabled)
        self.assertTrue(config.fail_closed)
        self.assertContains(resp, 'Đã bật quét virus')

    def test_switch_off_saves(self):
        fsc.save_config(enabled=True, fail_closed=True, admin_user=self.user)
        with patch('nas_storage.av_scan.ping', return_value=True):
            resp = self.client.post(
                reverse('audit:file_scan_save_config'), {}, follow=True,
            )
        config = FileScanConfig.get_solo()
        self.assertFalse(config.enabled)
        self.assertFalse(config.fail_closed)
        self.assertContains(resp, 'Đã tắt quét virus')

    def test_records_who_changed_it(self):
        with patch('nas_storage.av_scan.ping', return_value=True):
            self.client.post(reverse('audit:file_scan_save_config'), {'enabled': 'on'})
        self.assertEqual(FileScanConfig.get_solo().updated_by, self.user)



    def test_view_only_user_sees_no_form(self):
        RoleModulePermission.objects.update_or_create(
            role='EMPLOYEE',
            defaults={'module_permissions': {MODULE_AUDIT: {'view': True}}},
        )
        viewer = User.objects.create_user(username='viewer_scan', password='x')
        Profile.objects.filter(user=viewer).update(
            department=self.dept, role='EMPLOYEE', full_name='Viewer', is_employed=True,
        )
        client = Client(HTTP_HOST='testserver')
        client.force_login(viewer)
        with patch('nas_storage.av_scan.ping', return_value=True):
            resp = client.get(reverse('audit:login_security'), {'tab': 'filescan'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'chỉ có quyền xem')
        self.assertNotContains(resp, 'name="enabled"')
