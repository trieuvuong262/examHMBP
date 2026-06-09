from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_KIOTVIET
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


@override_settings(
    KIOTVIET_RETAILER='justsport',
    KIOTVIET_USE_LOCAL_MIRROR=True,
)
class KiotVietGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='KV Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['kiotviet'])

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_KIOTVIET] = {
            'view': True, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-kv-view',
            name='KiotViet view only',
            module_permissions=view_only,
        )

        no_access = dict(base)
        no_access[MODULE_KIOTVIET] = {
            'view': False, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        self.group_none = PermissionGroup.objects.create(
            slug='test-kv-none',
            name='KiotViet none',
            module_permissions=no_access,
        )

        self.view_user = self._user('kv_view', self.group_view)
        self.blocked_user = self._user('kv_none', self.group_none)
        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, group):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=group,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_view_user_can_open_customer_lookup(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('kiotviet:customer_lookup'))
        self.assertEqual(response.status_code, 200)

    def test_no_access_user_blocked_from_lookup(self):
        self.client.force_login(self.blocked_user)
        response = self.client.get(reverse('kiotviet:customer_lookup'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
