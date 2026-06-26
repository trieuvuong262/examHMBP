from django.contrib.auth.models import User
from django.test import TestCase

from nas_storage.folder_permissions_resolved import effective_folder_permissions
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder


class NasFolderTreeTests(TestCase):
    def setUp(self):
        self.root = NasShareFolder.objects.create(share_name='05_MARKETING', display_name='Marketing')
        self.child = NasShareFolder.objects.create(
            parent=self.root,
            share_name='05_MARKETING',
            sub_path='KD-MKT',
            display_name='KD MKT',
            inherits_permissions=True,
        )
        self.group = NasAccessGroup.objects.create(name='MKT', nas_principal='MKT')
        NasFolderPermission.objects.create(folder=self.root, group=self.group)

    def test_child_inherits_parent_permission(self):
        effective = effective_folder_permissions(self.child)
        self.assertEqual(len(effective), 1)
        self.assertEqual(effective[0].source, 'inherited')
        self.assertEqual(effective[0].permission.group_id, self.group.pk)

    def test_child_local_overrides_inherited(self):
        user = User.objects.create_user('lvanhthu', password='x')
        NasFolderPermission.objects.create(folder=self.child, user=user)
        effective = effective_folder_permissions(self.child)
        sources = {e.source for e in effective}
        self.assertIn('inherited', sources)
        self.assertIn('local', sources)

    def test_portal_path_label(self):
        self.assertEqual(self.child.portal_path_label(), '05_MARKETING/KD-MKT')

from unittest.mock import patch

from django.test import TestCase

from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import provision_portal_folder_on_nas


class NasFolderProvisionTests(TestCase):
    def setUp(self):
        self.root = NasShareFolder.objects.create(share_name='05_MARKETING', display_name='Marketing')

    @patch('nas_storage.nas_acl_apply.nas_acl_ssh_configured', return_value=True)
    @patch('nas_storage.nas_acl_apply.ensure_directory_on_nas', return_value='OK')
    def test_provision_child_mkdir(self, _mkdir, _ssh):
        child = NasShareFolder.objects.create(
            parent=self.root,
            share_name='05_MARKETING',
            sub_path='KD-MKT',
            display_name='KD',
        )
        result = provision_portal_folder_on_nas(child)
        self.assertEqual(result['action'], 'mkdir')
        _mkdir.assert_called_once()
