"""Tests portal browse-all theo NasAccessGroup."""

from django.contrib.auth.models import User
from django.test import TestCase

from hrm.models import Department, Profile
from nas_storage.models import NasAccessGroup, NasShareFolder, NasUserFolderAccess
from nas_storage.nas_paths import get_user_nas_roots
from nas_storage.portal_access import (
    sync_browse_all_share_permissions,
    user_has_portal_browse_all,
    user_nas_access_groups,
)


class PortalBrowseAllTests(TestCase):
    def setUp(self):
        self.dept_tgd, _ = Department.objects.get_or_create(name='Tổng giám đốc')
        self.dept_sx, _ = Department.objects.get_or_create(name='SẢN XUẤT')
        self.tgd_group = NasAccessGroup.objects.create(
            name='TGD',
            nas_principal='@TGD@ldap.justplay.local',
            portal_browse_all=True,
        )
        NasShareFolder.objects.create(share_name='01_BAN_GIAM_DOC', display_name='BGD')
        NasShareFolder.objects.create(share_name='07_SAN_XUAT', display_name='SX')

    def _user(self, username: str, dept: Department) -> User:
        user = User.objects.create_user(username, password='x')
        Profile.objects.create(user=user, full_name=username, department=dept, is_employed=True)
        return user

    def test_department_tgd_gets_browse_all(self):
        user = self._user('ductn', self.dept_tgd)
        self.assertTrue(user_has_portal_browse_all(user))
        roots = get_user_nas_roots(user)
        self.assertEqual(len(roots), 2)
        paths = {r.rel_path for r in roots}
        self.assertIn('01_BAN_GIAM_DOC', paths)
        self.assertIn('07_SAN_XUAT', paths)

    def test_extra_member_outside_department(self):
        user = self._user('ductn', self.dept_sx)
        self.assertFalse(user_has_portal_browse_all(user))
        self.tgd_group.portal_members.add(user)
        self.assertTrue(user_has_portal_browse_all(user))
        self.assertEqual(user_nas_access_groups(user).get(), self.tgd_group)

    def test_custom_folder_overrides_browse_all(self):
        user = self._user('ductn', self.dept_tgd)
        NasUserFolderAccess.objects.create(
            user=user,
            label='Rieng',
            rel_path='07_SAN_XUAT/ductn',
            is_active=True,
        )
        roots = get_user_nas_roots(user)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0].rel_path, '07_SAN_XUAT/ductn')

    def test_sync_browse_all_creates_read_permissions(self):
        from nas_storage.models import NasFolderPermission

        stats = sync_browse_all_share_permissions()
        self.assertEqual(stats['permissions_created'], 2)
        perms = NasFolderPermission.objects.filter(group=self.tgd_group)
        self.assertEqual(perms.count(), 2)
        self.assertTrue(all(p.perm_list_read for p in perms))
        self.assertFalse(any(p.perm_create_files for p in perms))

