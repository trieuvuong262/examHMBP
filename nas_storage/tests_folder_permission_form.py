from django.test import TestCase

from nas_storage.forms import NasFolderPermissionForm
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder


class NasFolderPermissionFormDuplicateTests(TestCase):
    def setUp(self):
        self.folder = NasShareFolder.objects.create(share_name='07_SAN_XUAT')
        self.group = NasAccessGroup.objects.create(name='SX', nas_principal='@SX@ldap.justplay.local')
        NasFolderPermission.objects.create(folder=self.folder, group=self.group)

    def test_rejects_duplicate_group_for_folder(self):
        form = NasFolderPermissionForm(
            data={
                'group': self.group.pk,
                'permission_type': 'allow',
                'apply_to': 'all',
                'preset': 'read_write',
            },
            folder=self.folder,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('group', form.errors)

    def test_create_form_hides_groups_with_existing_permission(self):
        form = NasFolderPermissionForm(folder=self.folder)
        self.assertNotIn(self.group.pk, list(form.fields['group'].queryset.values_list('pk', flat=True)))
from django.contrib.auth.models import User
from django.test import TestCase

from nas_storage.forms import NasFolderPermissionForm
from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder


class NasFolderPermissionUserFormTests(TestCase):
    def setUp(self):
        self.folder = NasShareFolder.objects.create(share_name='04_KINH_DOANH_CSKH')
        self.group = NasAccessGroup.objects.create(name='IT', nas_principal='@IT@ldap.justplay.local')
        self.user = User.objects.create_user('vuonglnt', 'v@test.local', 'pass')

    def test_create_user_permission(self):
        form = NasFolderPermissionForm(
            {
                'assignee_type': 'user',
                'user': self.user.pk,
                'permission_type': 'allow',
                'apply_to': 'all',
                'preset': 'read',
            },
            folder=self.folder,
        )
        self.assertTrue(form.is_valid(), form.errors)
        perm = form.save(commit=False)
        perm.folder = self.folder
        perm.save()
        self.assertEqual(perm.user_id, self.user.pk)
        self.assertIsNone(perm.group_id)
        self.assertEqual(perm.resolved_nas_principal(), 'vuonglnt@ldap.justplay.local')

    def test_duplicate_user_rejected(self):
        NasFolderPermission.objects.create(folder=self.folder, user=self.user)
        form = NasFolderPermissionForm(
            {
                'assignee_type': 'user',
                'user': self.user.pk,
                'permission_type': 'allow',
                'apply_to': 'all',
                'preset': 'read',
            },
            folder=self.folder,
        )
        self.assertFalse(form.is_valid())
