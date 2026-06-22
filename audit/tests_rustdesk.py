from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
import json

from audit.forms_rustdesk import RustDeskHostForm
from audit.models import RustDeskHost
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_AUDIT
from hrm.permissions import ROLE_EMPLOYEE


class RustdeskConnectTests(SimpleTestCase):
    @override_settings(
        RUSTDESK_PUBLIC_HOST='rd.justplay.vn',
        RUSTDESK_PUBLIC_KEY='0KDL7LQhVpSud8Y2ciHOt16Jv+XWXGlc75goPVN0Zkk=',
        RUSTDESK_CLIENT_PASSWORD='',
    )
    def test_build_connect_url_with_password(self):
        from audit.services.rustdesk_connect import build_rustdesk_connect_url

        url = build_rustdesk_connect_url('258 599 030', 'secret&x')
        self.assertEqual(url, 'rustdesk://connection/new/258599030?password=secret%26x')

    @override_settings(
        RUSTDESK_PUBLIC_HOST='rd.justplay.vn',
        RUSTDESK_PUBLIC_KEY='0KDL7LQhVpSud8Y2ciHOt16Jv+XWXGlc75goPVN0Zkk=',
        RUSTDESK_CLIENT_PASSWORD='',
    )
    def test_build_connect_url_without_password(self):
        from audit.services.rustdesk_connect import build_rustdesk_connect_url

        url = build_rustdesk_connect_url('258599030', '')
        self.assertEqual(url, 'rustdesk://connection/new/258599030')

    @override_settings(RUSTDESK_PUBLIC_KEY='', RUSTDESK_CLIENT_PASSWORD='')
    def test_build_connect_url_fallback_without_key(self):
        from audit.services.rustdesk_connect import build_rustdesk_connect_url

        url = build_rustdesk_connect_url('258599030', 'pw')
        self.assertEqual(url, 'rustdesk://connection/new/258599030?password=pw')

    @override_settings(
        RUSTDESK_CLIENT_PASSWORD='env-pw',
        RUSTDESK_APPROVE_MODE='password',
    )
    def test_build_connect_url_prefers_env_over_host_password(self):
        from audit.services.rustdesk_connect import build_rustdesk_connect_url

        url = build_rustdesk_connect_url('258599030', 'old-db-pw')
        self.assertEqual(url, 'rustdesk://connection/new/258599030?password=env-pw')

    @override_settings(
        RUSTDESK_CLIENT_PASSWORD='env-pw',
        RUSTDESK_APPROVE_MODE='password',
    )
    def test_build_connect_url_uses_env_password_fallback(self):
        from audit.services.rustdesk_connect import build_rustdesk_connect_url

        url = build_rustdesk_connect_url('258599030', '')
        self.assertEqual(url, 'rustdesk://connection/new/258599030?password=env-pw')

    @override_settings(RUSTDESK_APPROVE_MODE='click')
    def test_build_connect_url_click_mode_no_password(self):
        from audit.services.rustdesk_connect import build_rustdesk_connect_url

        url = build_rustdesk_connect_url('258599030', 'pw123')
        self.assertEqual(url, 'rustdesk://connection/new/258599030')


class RustdeskHostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT Sysadmin', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=cls.dept,
            modules=['audit'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_AUDIT] = {
            'view': True,
            'menus': {
                'rustdesk': {
                    'view': True,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                },
            },
        }
        editor = dict(base)
        editor[MODULE_AUDIT] = {
            'view': True,
            'menus': {
                'rustdesk': {
                    'view': True,
                    'create': True,
                    'update': True,
                    'delete': False,
                    'export': False,
                },
            },
        }
        cls.group_view = PermissionGroup.objects.create(
            slug='test-audit-rd-view',
            name='Audit RD view',
            module_permissions=view_only,
        )
        cls.group_edit = PermissionGroup.objects.create(
            slug='test-audit-rd-edit',
            name='Audit RD edit',
            module_permissions=editor,
        )

        cls.view_user = User.objects.create_user('audrdview', password='x')
        cls.edit_user = User.objects.create_user('audrdedit', password='x')
        view_profile = Profile.objects.get(user=cls.view_user)
        view_profile.department = cls.dept
        view_profile.role = ROLE_EMPLOYEE
        view_profile.permission_group = cls.group_view
        view_profile.save()
        edit_profile = Profile.objects.get(user=cls.edit_user)
        edit_profile.department = cls.dept
        edit_profile.role = ROLE_EMPLOYEE
        edit_profile.permission_group = cls.group_edit
        edit_profile.save()

        cls.host = RustDeskHost.objects.create(
            name='PC Kế toán',
            rustdesk_id='258599030',
            rustdesk_password='pw123',
        )

    def setUp(self):
        self.client = Client(HTTP_HOST='testserver')

    def test_rustdesk_id_normalizes_in_form(self):
        form = RustDeskHostForm(data={
            'name': 'Test',
            'hostname': '',
            'ip_address': '',
            'rustdesk_id': '111222333',
            'rustdesk_password': 'abc',
            'department_text': '',
            'assigned_user_text': '',
            'notes': '',
            'device': '',
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['rustdesk_id'], '111222333')

    def test_list_page_shows_host(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('audit:rustdesk_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '258 599 030')
        self.assertContains(response, 'rd.justplay.vn')

    def test_edit_user_can_edit_rustdesk_menu(self):
        from hrm.menu_permissions import user_can_edit_menu, user_can_update_menu

        self.edit_user.refresh_from_db()
        self.assertTrue(user_can_update_menu(self.edit_user, MODULE_AUDIT, 'rustdesk'))
        self.assertTrue(user_can_edit_menu(self.edit_user, MODULE_AUDIT, 'rustdesk'))

    @override_settings(
        RUSTDESK_PUBLIC_HOST='rd.justplay.vn',
        RUSTDESK_PUBLIC_KEY='test-public-key',
    )
    def test_edit_user_sees_connect_link(self):
        self.client.force_login(self.edit_user)
        response = self.client.get(reverse('audit:rustdesk_list'))
        self.assertContains(response, 'rustdesk://connection/new/258599030')
        self.assertContains(response, 'Kết nối')

    def test_view_only_no_connect_link(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('audit:rustdesk_list'))
        self.assertNotContains(response, 'rustdesk://')
        self.assertContains(response, 'Chỉ IT được kết nối')

    @override_settings(
        RUSTDESK_PUBLIC_HOST='rd.justplay.vn',
        RUSTDESK_PUBLIC_KEY='test-public-key',
    )
    def test_host_connect_url_property(self):
        self.assertEqual(
            self.host.rustdesk_connect_url,
            'rustdesk://connection/new/258599030?password=pw123',
        )

    def test_submenu_registry_has_rustdesk(self):
        from hrm.submenu_registry import get_module_submenus

        keys = [m['key'] for m in get_module_submenus('audit')]
        self.assertIn('rustdesk', keys)


class RustdeskEnrollApiTests(TestCase):
    @override_settings(
        RUSTDESK_ENROLL_SECRET='test-enroll-secret',
    )
    def test_enroll_api_creates_host(self):
        client = Client()
        payload = {
            'enroll_secret': 'test-enroll-secret',
            'rustdesk_id': '258599030',
            'rustdesk_password': 'pw123',
            'hostname': 'PC-TEST',
            'ip_address': '10.0.0.5',
        }
        resp = client.post(
            '/nhat-ky/rustdesk/api/dang-ky/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        host = RustDeskHost.objects.get(rustdesk_id='258599030')
        self.assertEqual(host.hostname, 'PC-TEST')
        self.assertEqual(host.rustdesk_password, 'pw123')

    @override_settings(RUSTDESK_ENROLL_SECRET='test-enroll-secret')
    def test_enroll_api_rejects_bad_secret(self):
        client = Client()
        resp = client.post(
            '/nhat-ky/rustdesk/api/dang-ky/',
            data=json.dumps({'enroll_secret': 'wrong', 'rustdesk_id': '111222333'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)


class RustdeskDownloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT DL', sort_order=1)
        DepartmentMenuPermission.objects.create(department=cls.dept, modules=['audit'])
        perms = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        perms[MODULE_AUDIT] = {
            'view': True,
            'menus': {'rustdesk': {'view': True, 'create': False, 'update': False, 'delete': False, 'export': False}},
        }
        cls.group = PermissionGroup.objects.create(
            slug='test-audit-rd-dl',
            name='Audit RD dl',
            module_permissions=perms,
        )
        cls.user = User.objects.create_user('audrddl', password='x')
        profile = Profile.objects.get(user=cls.user)
        profile.department = cls.dept
        profile.role = ROLE_EMPLOYEE
        profile.permission_group = cls.group
        profile.save()

    def setUp(self):
        self.client = Client(HTTP_HOST='testserver')

    @override_settings(
        RUSTDESK_ENROLL_SECRET='enroll-secret',
        RUSTDESK_PUBLIC_KEY='public-key',
        RUSTDESK_CLIENT_PASSWORD='client-pw',
        RUSTDESK_PUBLIC_HOST='rd.justplay.vn',
    )
    def test_windows_download_is_zip_with_substituted_scripts(self):
        import io
        import zipfile

        self.client.force_login(self.user)
        resp = self.client.get(reverse('audit:rustdesk_download_setup') + '?os=win')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {'JustPlay-RustDesk-Setup.cmd', 'JustPlay-RustDesk-Setup.ps1'})
            cmd = archive.read('JustPlay-RustDesk-Setup.cmd').decode('utf-8')
            ps1 = archive.read('JustPlay-RustDesk-Setup.ps1').decode('utf-8')
        self.assertIn('\r\n', cmd)
        self.assertIn('%LOCALAPPDATA%\\JustPlay\\RustDesk-Setup', cmd)
        self.assertNotIn('__ENROLL_SECRET__', ps1)
        self.assertIn('enroll-secret', ps1)
        self.assertIn('public-key', ps1)

    @override_settings(
        RUSTDESK_ENROLL_SECRET='enroll-secret',
        RUSTDESK_PUBLIC_KEY='public-key',
        RUSTDESK_CLIENT_PASSWORD='client-pw',
        RUSTDESK_PUBLIC_HOST='rd.justplay.vn',
    )
    def test_linux_download_has_banner_and_lf(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('audit:rustdesk_download_setup') + '?os=linux')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertTrue(body.startswith('#!/usr/bin/env bash'))
        self.assertIn('JustPlay - Cai dat RustDesk (Linux)', body)
        self.assertNotIn('\r\n', body)
        self.assertNotIn('__ENROLL_SECRET__', body)
