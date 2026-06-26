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

class NasFolderNestedPathTests(TestCase):
    def setUp(self):
        self.root = NasShareFolder.objects.create(share_name='05_MARKETING', display_name='Marketing')
        self.mid = NasShareFolder.objects.create(
            parent=self.root, share_name='05_MARKETING', sub_path='KD-MKT', display_name='KD',
        )

    def test_nested_full_path(self):
        deep = NasShareFolder.objects.create(
            parent=self.mid, share_name='05_MARKETING', sub_path='_CHUNG', display_name='Chung',
        )
        self.assertEqual(deep.full_sub_path_from_share(), 'KD-MKT/_CHUNG')
        self.assertEqual(deep.portal_path_label(), '05_MARKETING/KD-MKT/_CHUNG')

    def test_build_tree_nested(self):
        from nas_storage.folder_tree import build_folder_tree
        NasShareFolder.objects.create(
            parent=self.mid, share_name='05_MARKETING', sub_path='_CHUNG', display_name='Chung',
        )
        tree = build_folder_tree(list(NasShareFolder.objects.all()))
        self.assertEqual(len(tree), 1)
        self.assertEqual(len(tree[0].children), 1)
        self.assertEqual(len(tree[0].children[0].children), 1)


class ImportSharesFromNasTests(TestCase):
    def test_import_skips_child_with_same_share_name(self):
        from unittest.mock import patch
        from django.contrib.auth.models import User
        from django.test import Client
        from django.urls import reverse
        from nas_storage.models import NasShareFolder

        root = NasShareFolder.objects.create(share_name='test', display_name='Test')
        NasShareFolder.objects.create(
            parent=root, share_name='test', sub_path='sub1', display_name='Sub',
        )
        user = User.objects.create_superuser('admimport', '', 'x')
        with patch('nas_storage.views_permissions.user_can_update_menu', return_value=True):
            with patch(
                'nas_storage.views_permissions.discover_share_tree_from_nas',
                return_value=[
                    {'share_name': 'test', 'display_name': 'Test', 'children': []},
                    {'share_name': 'NEW_SHARE', 'display_name': 'NEW_SHARE', 'children': []},
                ],
            ):
                client = Client()
                client.force_login(user)
                r = client.post(reverse('nas_storage:import_shares'))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            NasShareFolder.objects.filter(share_name='NEW_SHARE', parent__isnull=True).count(),
            1,
        )
