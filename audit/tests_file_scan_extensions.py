"""Tests: danh sách đuôi + giới hạn dung lượng cấu hình từ DB."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audit.file_scan_config import (
    configured_allowed_extensions,
    configured_max_bytes,
    parse_extensions_input,
    save_allowed_extensions,
    save_config,
    upload_limits_mb,
)
from audit.models import FileScanConfig
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_AUDIT
from nas_storage.upload_guard import MB, UploadRejected, validate_upload

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 40
PDF = b'%PDF-1.4 minimal'
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 20


class ParseExtensionsTests(TestCase):
    def test_normalize_and_dedupe(self):
        valid, rejected = parse_extensions_input('PDF, .jpg\nDOCX\n.pdf\n.exe\nbad!!')
        self.assertEqual(valid, ['.docx', '.jpg', '.pdf'])
        self.assertIn('.exe', rejected)
        self.assertIn('bad!!', rejected)


class ConfiguredExtensionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('it', password='x')

    def test_empty_db_uses_code_defaults(self):
        cfg = FileScanConfig.get_solo()
        self.assertEqual(cfg.allowed_extensions, [])
        exts = configured_allowed_extensions()
        self.assertIn('.pdf', exts)
        self.assertIn('.psd', exts)
        self.assertNotIn('.exe', exts)

    def test_custom_list_filters_upload(self):
        save_allowed_extensions(extensions=['.pdf', '.png'], admin_user=self.user)
        self.assertEqual(configured_allowed_extensions(), ['.pdf', '.png'])

        ok = SimpleUploadedFile('a.pdf', PDF, content_type='application/pdf')
        name = validate_upload(ok, scan=False)
        self.assertTrue(name.endswith('.pdf'))

        bad = SimpleUploadedFile('photo.jpg', JPEG, content_type='image/jpeg')
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(bad, scan=False)
        self.assertIn('không được phép', str(ctx.exception).lower())

    def test_dangerous_never_saved(self):
        save_allowed_extensions(
            extensions=['.pdf', '.html', '.js', '.exe'],
            admin_user=self.user,
        )
        self.assertEqual(configured_allowed_extensions(), ['.pdf'])

    def test_reset_default(self):
        save_allowed_extensions(extensions=['.pdf'], admin_user=self.user)
        save_allowed_extensions(extensions=[], admin_user=self.user, reset_default=True)
        cfg = FileScanConfig.get_solo()
        self.assertEqual(cfg.allowed_extensions, [])
        self.assertIn('.docx', configured_allowed_extensions())


class ConfiguredMaxSizeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('it_size', password='x')

    def test_db_limit_rejects_oversize_image(self):
        save_config(
            enabled=False,
            fail_closed=False,
            admin_user=self.user,
            max_mb_image=1,
            max_mb_doc=30,
            max_mb_archive=50,
            max_mb_design=100,
            max_mb_video=200,
        )
        self.assertEqual(configured_max_bytes('image'), 1 * MB)
        self.assertEqual(upload_limits_mb()['image'], 1)

        big = SimpleUploadedFile('big.png', PNG + (b'0' * (2 * MB)), content_type='image/png')
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(big, scan=False)
        self.assertIn('vượt giới hạn', ' '.join(ctx.exception.messages))

    def test_db_limit_accepts_within_size(self):
        save_config(
            enabled=False,
            fail_closed=False,
            admin_user=self.user,
            max_mb_image=5,
        )
        ok = SimpleUploadedFile('ok.png', PNG, content_type='image/png')
        self.assertEqual(validate_upload(ok, scan=False), 'ok.png')

    @override_settings(UPLOAD_MAX_BYTES_IMAGE=50 * MB)
    def test_db_overrides_env_upload_max(self):
        save_config(
            enabled=False,
            fail_closed=False,
            admin_user=self.user,
            max_mb_image=1,
        )
        big = SimpleUploadedFile('big.png', PNG + (b'0' * (2 * MB)), content_type='image/png')
        with self.assertRaises(UploadRejected):
            validate_upload(big, scan=False)


class FileScanConfigFormTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='IT Form', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['audit'])
        RoleModulePermission.objects.update_or_create(
            role='ADMIN',
            defaults={'module_permissions': {
                MODULE_AUDIT: {'view': True, 'edit': True, 'export': True},
            }},
        )
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username='it_form', email='a@b.c', password='x',
        )
        Profile.objects.filter(user=self.user).update(
            department=self.dept, role='ADMIN', full_name='IT Form', is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_save_max_mb_via_post(self):
        with patch('nas_storage.av_scan.ping', return_value=True):
            resp = self.client.post(
                reverse('audit:file_scan_save_config'),
                {
                    'enabled': 'on',
                    'max_mb_image': '7',
                    'max_mb_doc': '11',
                    'max_mb_archive': '22',
                    'max_mb_design': '33',
                    'max_mb_video': '44',
                },
                follow=True,
            )
        self.assertEqual(resp.status_code, 200)
        cfg = FileScanConfig.get_solo()
        self.assertEqual(cfg.max_mb_image, 7)
        self.assertEqual(cfg.max_mb_doc, 11)
        self.assertEqual(cfg.max_mb_archive, 22)
        self.assertEqual(cfg.max_mb_design, 33)
        self.assertEqual(cfg.max_mb_video, 44)

    def test_save_extensions_via_post(self):
        resp = self.client.post(
            reverse('audit:file_scan_save_extensions'),
            {'allowed_extensions': '.pdf\n.png\n.exe'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(configured_allowed_extensions(), ['.pdf', '.png'])

    def test_reset_extensions_via_post(self):
        save_allowed_extensions(extensions=['.pdf'], admin_user=self.user)
        resp = self.client.post(
            reverse('audit:file_scan_save_extensions'),
            {'reset_default': '1'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FileScanConfig.get_solo().allowed_extensions, [])
        self.assertIn('.docx', configured_allowed_extensions())

    def test_filescan_tab_shows_size_fields(self):
        with patch('nas_storage.av_scan.ping', return_value=False):
            resp = self.client.get(reverse('audit:login_security'), {'tab': 'filescan'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="max_mb_image"')
        self.assertContains(resp, 'name="allowed_extensions"')
