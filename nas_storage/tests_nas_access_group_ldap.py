from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from audit.services.nas_ldap_sync import (
    _portal_ldap_group_names,
    _portal_managed_ldap_group_names,
    nas_ldap_group_for_department,
    sync_nas_access_group_to_ldap,
)
from hrm.department_permission_templates import department_name_to_code
from hrm.models import Department, Profile
from nas_storage.dept_nas_config import nas_group_for_portal_department
from nas_storage.forms import NasAccessGroupForm
from nas_storage.models import NasAccessGroup
from nas_storage.portal_access import users_auto_in_nas_group


class ItDepartmentNasMappingTests(TestCase):
    def test_it_cntt_maps_to_it_group(self):
        self.assertEqual(department_name_to_code('IT / CNTT'), 'it')
        self.assertEqual(department_name_to_code('CNTT'), 'it')
        self.assertEqual(department_name_to_code('IT'), 'it')
        self.assertEqual(nas_group_for_portal_department('IT / CNTT'), 'IT')
        self.assertEqual(nas_ldap_group_for_department('IT / CNTT'), 'IT')

    def test_it_cntt_users_are_auto_members(self):
        dept, _ = Department.objects.get_or_create(
            name='IT / CNTT',
            defaults={'sort_order': 99},
        )
        user = User.objects.create_user('it.nv01', password='x')
        profile = user.profile
        profile.full_name = 'IT NV 01'
        profile.department = dept
        profile.is_employed = True
        profile.save()
        NasAccessGroup.objects.create(name='IT', sort_order=1)
        autos = users_auto_in_nas_group('IT')
        self.assertIn(user, autos)


class NasAccessGroupFormTests(TestCase):
    def test_rejects_unsafe_ldap_name(self):
        form = NasAccessGroupForm(data={
            'name': 'Nhom IT',
            'sort_order': 0,
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_accepts_ldap_safe_name(self):
        form = NasAccessGroupForm(data={
            'name': 'QA-1',
            'sort_order': 0,
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)


@override_settings(
    NAS_LDAP_SYNC_ENABLED=True,
    NAS_LDAP_HOST='ldap.test',
    NAS_LDAP_BIND_DN='uid=root,cn=users,dc=test',
    NAS_LDAP_BIND_PASSWORD='secret',
    NAS_LDAP_BASE_DN='dc=test',
)
class NasAccessGroupLdapSyncTests(TestCase):
    def test_custom_group_is_managed_and_on_user(self):
        group = NasAccessGroup.objects.create(name='QA-LAB', sort_order=80)
        user = User.objects.create_user('qa.nv01', password='x')
        profile = user.profile
        profile.full_name = 'QA NV'
        profile.is_employed = True
        profile.save()
        group.portal_members.add(user)
        self.assertIn('QA-LAB', _portal_managed_ldap_group_names())
        self.assertIn('QA-LAB', _portal_ldap_group_names(user))

    def test_save_creates_ldap_group_when_no_member_changes(self):
        group = NasAccessGroup.objects.create(name='QA-LAB', sort_order=80)
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = False
        with patch('audit.services.nas_ldap_sync.nas_ldap_configured', return_value=True), \
             patch('audit.services.nas_ldap_sync._ldap_connection', return_value=conn), \
             patch('audit.services.nas_ldap_sync._group_exists', return_value=False), \
             patch('audit.services.nas_ldap_sync._ensure_group', return_value='cn=QA-LAB,cn=groups,dc=test') as ensure, \
             patch('audit.services.nas_ldap_sync._ensure_department_groups_on_conn', return_value=[]):
            stats = sync_nas_access_group_to_ldap(group, created=True)
        self.assertEqual(stats['status'], 'ok')
        self.assertTrue(stats['group_created'])
        ensure.assert_any_call(conn, 'QA-LAB', description='Nhóm NAS QA-LAB')
