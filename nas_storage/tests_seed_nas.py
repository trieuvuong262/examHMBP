from django.test import TestCase, override_settings

from nas_storage.dept_nas_config import (
    DEPT_NAS_SPECS,
    NAS_USER_DESCRIPTION_TO_GROUP,
    nas_group_for_portal_department,
    nas_group_for_user_description,
    nas_principal_for_group,
)
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder
from nas_storage.seed_nas_permissions import seed_nas_permissions


class DeptNasConfigTests(TestCase):
    def test_portal_department_to_group(self):
        self.assertEqual(nas_group_for_portal_department('SẢN XUẤT'), 'SX')
        self.assertEqual(nas_group_for_portal_department('KINH DOANH - MARKETING'), 'MKT')
        self.assertIsNone(nas_group_for_portal_department(''))

    def test_dsm_description_fallback(self):
        self.assertEqual(nas_group_for_user_description('KD-MKT'), 'MKT')
        self.assertEqual(NAS_USER_DESCRIPTION_TO_GROUP['RnD'], 'RnD')

    @override_settings(NAS_LDAP_DOMAIN='ldap.justplay.local')
    def test_nas_principal(self):
        self.assertEqual(nas_principal_for_group('SX'), '@SX@ldap.justplay.local')


class SeedNasPermissionsTests(TestCase):
    def test_seed_creates_groups_shares_permissions(self):
        stats = seed_nas_permissions()
        self.assertGreater(stats['groups_created'], 0)
        self.assertGreater(stats['folders_created'], 0)
        self.assertGreater(stats['permissions_created'], 0)

        sx = NasAccessGroup.objects.get(name='SX')
        folder = NasShareFolder.objects.get(share_name='07_SAN_XUAT')
        perm = NasFolderPermission.objects.get(folder=folder, group=sx)
        self.assertTrue(perm.perm_list_read)
        self.assertTrue(perm.perm_create_files)

    def test_seed_idempotent(self):
        seed_nas_permissions()
        stats = seed_nas_permissions()
        self.assertEqual(stats['groups_created'], 0)
        self.assertEqual(stats['permissions_created'], 0)

    def test_all_dept_specs_have_groups(self):
        seed_nas_permissions()
        for spec in DEPT_NAS_SPECS:
            self.assertTrue(NasAccessGroup.objects.filter(name=spec.nas_group).exists())
