from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from hrm.menu_permissions import resolve_menu_from_request
from hrm.module_permissions import MODULE_NAS_STORAGE
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import _share_access_level
from nas_storage.permission_defs import flags_from_preset, has_write_access


class NasSubmenuPathTests(TestCase):
    def test_resolve_permissions_path(self):
        module, menu = resolve_menu_from_request('/thu-muc-nas/phan-quyen/', None)
        self.assertEqual(module, MODULE_NAS_STORAGE)
        # Hub phân quyền defer menu check — view tự kiểm tra quyền `permissions`.
        self.assertIsNone(menu)

    def test_resolve_browse_path(self):
        module, menu = resolve_menu_from_request('/thu-muc-nas/', None)
        self.assertEqual(module, MODULE_NAS_STORAGE)
        self.assertEqual(menu, 'browse')


class NasPermissionModelTests(TestCase):
    def test_resolved_nas_principal_default(self):
        with override_settings(NAS_LDAP_DOMAIN='ldap.justplay.local'):
            g = NasAccessGroup.objects.create(name='SX')
            self.assertEqual(g.resolved_nas_principal(), '@SX@ldap.justplay.local')

    def test_share_access_level_read_write(self):
        folder = NasShareFolder.objects.create(share_name='07_SAN_XUAT')
        group = NasAccessGroup.objects.create(name='SX', nas_principal='@SX@ldap.justplay.local')
        perm = NasFolderPermission.objects.create(folder=folder, group=group)
        self.assertEqual(_share_access_level(perm), 'RW')

    def test_share_access_level_read_only(self):
        folder = NasShareFolder.objects.create(share_name='07_SAN_XUAT')
        group = NasAccessGroup.objects.create(name='KHSX')
        flags = flags_from_preset('read')
        perm = NasFolderPermission.objects.create(folder=folder, group=group, **flags)
        self.assertEqual(_share_access_level(perm), 'RO')
        self.assertFalse(has_write_access(flags))


class PermissionEditorViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('nasperm', 'nasperm@test.local', 'pass')
        self.client = Client()
        self.client.force_login(self.user)
        self.folder = NasShareFolder.objects.create(share_name='07_SAN_XUAT')
        self.group = NasAccessGroup.objects.create(name='SX', nas_principal='@SX@ldap.justplay.local')
        self.perm = NasFolderPermission.objects.create(folder=self.folder, group=self.group)

    @patch('nas_storage.views_permissions.user_can_update_menu', return_value=True)
    @patch('nas_storage.views_permissions.user_can_access_menu', return_value=True)
    def test_permission_edit_page_renders(self, _mock_access, _mock_perm):
        url = reverse('nas_storage:permission_edit', args=[self.folder.pk, self.perm.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sửa quyền')
        self.assertContains(response, 'perm_traverse')
        self.assertContains(response, 'jp-portal-pills')
        self.assertContains(response, 'Mức quyền')
