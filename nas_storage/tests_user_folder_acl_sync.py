from django.test import TestCase
from django.contrib.auth.models import User

from nas_storage.models import NasShareFolder, NasUserFolderAccess, NasUserFolderAcl
from nas_storage.user_folders import ensure_portal_link_for_acl, portal_rel_path_for_acl


class PortalLinkFromAclTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dinhgiang', 'dg@test.local', 'pass')
        self.folder = NasShareFolder.objects.create(share_name='05_MARKETING')

    def test_portal_rel_path(self):
        self.assertEqual(
            portal_rel_path_for_acl(share_name='05_MARKETING', sub_path='Dinhgiang'),
            '05_MARKETING/Dinhgiang',
        )

    def test_ensure_portal_link_for_acl(self):
        grant = NasUserFolderAcl.objects.create(
            user=self.user,
            folder=self.folder,
            sub_path='Dinhgiang',
        )
        row, created = ensure_portal_link_for_acl(grant)
        self.assertTrue(created)
        self.assertEqual(row.rel_path, '05_MARKETING/Dinhgiang')
        self.assertTrue(NasUserFolderAccess.objects.filter(user=self.user, is_active=True).exists())
