from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from audit.services.nas_ldap_sync import (
    DEFAULT_LDAP_GROUP,
    DEPARTMENT_LDAP_GROUPS,
    PORTAL_CODE_TO_LDAP_GROUP,
    _should_sync_user,
    nas_ldap_group_for_department,
    primary_ldap_group_for_department,
    provision_ldap_user,
)
from hrm.models import Department, Profile


@override_settings(
    NAS_LDAP_SYNC_ENABLED=True,
    NAS_LDAP_HOST='ldap.test',
    NAS_LDAP_BIND_DN='uid=root,cn=users,dc=test',
    NAS_LDAP_BIND_PASSWORD='secret',
    NAS_LDAP_BASE_DN='dc=test',
)
class NasLdapMappingTests(TestCase):
    def test_department_group_mapping(self):
        self.assertEqual(nas_ldap_group_for_department('HÀNH CHÍNH NHÂN SỰ'), 'HCNS')
        self.assertEqual(nas_ldap_group_for_department('KINH DOANH - MARKETING'), 'MKT')
        self.assertEqual(nas_ldap_group_for_department('R&D'), 'RnD')
        self.assertEqual(nas_ldap_group_for_department('IT'), 'IT')
        self.assertIsNone(nas_ldap_group_for_department('Phòng lạ'))

    def test_portal_codes_cover_department_groups(self):
        self.assertEqual(set(PORTAL_CODE_TO_LDAP_GROUP.values()), set(DEPARTMENT_LDAP_GROUPS))

    def test_primary_group_for_nas_display(self):
        self.assertEqual(primary_ldap_group_for_department('SX'), 'SX')
        self.assertEqual(primary_ldap_group_for_department('IT'), 'IT')
        self.assertEqual(primary_ldap_group_for_department(None), DEFAULT_LDAP_GROUP)
        self.assertEqual(primary_ldap_group_for_department('unknown'), DEFAULT_LDAP_GROUP)

    def test_should_skip_admin_and_inactive(self):
        dept, _ = Department.objects.get_or_create(name='IT LDAP Test', defaults={'sort_order': 99})
        admin = User.objects.create_user('admin', password='x')
        Profile.objects.create(user=admin, full_name='Admin', department=dept, is_employed=True)
        self.assertFalse(_should_sync_user(admin))

        user = User.objects.create_user('nv01', password='x')
        Profile.objects.create(user=user, full_name='NV 01', department=dept, is_employed=False)
        self.assertFalse(_should_sync_user(user))

        user.is_active = False
        user.save(update_fields=['is_active'])
        Profile.objects.filter(user=user).update(is_employed=True)
        user.refresh_from_db()
        self.assertFalse(_should_sync_user(user))


@override_settings(NAS_LDAP_SYNC_ENABLED=False)
class NasLdapProvisionSkipTests(TestCase):
    def test_provision_skipped_when_disabled(self):
        user = User.objects.create_user('nv02', password='x')
        dept, _ = Department.objects.get_or_create(name='IT LDAP Test 2', defaults={'sort_order': 98})
        Profile.objects.create(user=user, full_name='NV 02', department=dept, is_employed=True)
        result = provision_ldap_user(user, password='abc')
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['reason'], 'not_configured')
