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
