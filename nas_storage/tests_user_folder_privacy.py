"""NAS user-folder privacy tests."""

from django.contrib.auth.models import User
from django.test import TestCase

from hrm.models import Department, Profile
from nas_storage.models import (
    NasAccessGroup,
    NasFolderPermission,
    NasShareFolder,
    NasUserFolderAccess,
    NasUserFolderAcl,
)
from nas_storage.nas_paths import NasPathError, get_user_nas_roots, resolve_nas_path
from nas_storage.permission_defs import flags_from_preset
from nas_storage.user_folder_privacy import (
    filter_listing_folders_for_user,
    user_can_access_private_nas_rel,
)


class UserFolderPrivacyTests(TestCase):
    def setUp(self):
        self.dept, _ = Department.objects.get_or_create(name='KINH DOANH - MARKETING', defaults={'sort_order': 1})
        self.mkt = NasAccessGroup.objects.create(name='MKT', nas_principal='@MKT@ldap.justplay.local')
        self.share = NasShareFolder.objects.create(share_name='05_MARKETING', display_name='Marketing')
        NasFolderPermission.objects.create(
            folder=self.share,
            group=self.mkt,
            permission_type='allow',
            **flags_from_preset('read'),
        )
        self.owner = self._user('lvanhthu')
        self.other = self._user('nhipt')
        NasUserFolderAcl.objects.create(
            user=self.owner,
            folder=self.share,
            sub_path='lvanhthu',
            is_active=True,
        )
        NasUserFolderAccess.objects.create(
            user=self.owner,
            label='Rieng',
            rel_path='05_MARKETING/lvanhthu',
            is_active=True,
        )

    def _user(self, username: str) -> User:
        user = User.objects.create_user(username, password='x')
        Profile.objects.update_or_create(
            user=user,
            defaults={'department': self.dept, 'full_name': username, 'is_employed': True},
        )
        user.refresh_from_db()
        return user

    def test_private_path_owner_only(self):
        self.assertTrue(user_can_access_private_nas_rel(self.owner, '05_MARKETING/lvanhthu'))
        self.assertFalse(user_can_access_private_nas_rel(self.other, '05_MARKETING/lvanhthu'))

    def test_filter_hides_private_folder_from_other_user(self):
        folders = [{'name': 'lvanhthu', 'is_dir': True}, {'name': '_CHUNG', 'is_dir': True}]
        visible = filter_listing_folders_for_user(self.other, '05_MARKETING', folders)
        self.assertEqual([f['name'] for f in visible], ['_CHUNG'])

    def test_resolve_nas_path_blocks_other_user_on_private_folder(self):
        with self.assertRaises(NasPathError):
            resolve_nas_path(self.other, '05_MARKETING/lvanhthu')

    def test_group_member_gets_share_root_not_owner_custom_roots(self):
        owner_roots = {r.rel_path for r in get_user_nas_roots(self.owner)}
        other_roots = {r.rel_path for r in get_user_nas_roots(self.other)}
        self.assertEqual(owner_roots, {'05_MARKETING/lvanhthu'})
        self.assertEqual(other_roots, {'05_MARKETING'})
