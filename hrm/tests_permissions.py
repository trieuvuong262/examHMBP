from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_GUIDE, MODULE_PERMISSIONS
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class PermissionsModuleGranularTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Perm Config Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['permissions'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_PERMISSIONS] = {
            'view': True, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-perm-view',
            name='Permissions view only',
            module_permissions=view_only,
        )

        editor = dict(base)
        editor[MODULE_PERMISSIONS] = {
            'view': True, 'create': True, 'update': True, 'delete': False, 'export': False,
        }
        self.group_editor = PermissionGroup.objects.create(
            slug='test-perm-editor',
            name='Permissions editor',
            module_permissions=editor,
        )

        self.view_user = self._user('perm_view', self.group_view)
        self.editor_user = self._user('perm_editor', self.group_editor)
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

    def test_view_only_can_open_permission_config(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('permission_config'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_group_add(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('permission_group_add'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_group_add(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('permission_group_add'))
        self.assertEqual(response.status_code, 200)


class GuideGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Guide Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['guide'])

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_GUIDE] = {
            'view': True, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-guide-view',
            name='Guide view only',
            module_permissions=view_only,
        )

        editor = dict(base)
        editor[MODULE_GUIDE] = {
            'view': True, 'create': False, 'update': True, 'delete': False, 'export': False,
        }
        self.group_editor = PermissionGroup.objects.create(
            slug='test-guide-editor',
            name='Guide editor',
            module_permissions=editor,
        )

        self.view_user = self._user('guide_view', self.group_view)
        self.editor_user = self._user('guide_editor', self.group_editor)
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

    def test_view_only_can_open_guide(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('user_guide'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_guide_edit(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('user_guide_edit'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_guide_edit(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('user_guide_edit'))
        self.assertEqual(response.status_code, 200)
