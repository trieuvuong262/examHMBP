from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL, user_can_access_module
from hrm.permissions import ROLE_EMPLOYEE


class KhoNplPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_viewer', password='test')
        Profile.objects.filter(user=self.user).update(
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.group = PermissionGroup.objects.create(
            name='NPL Test',
            module_permissions={
                MODULE_KHO_NPL: {
                    'view': True,
                    'create': True,
                    'update': True,
                    'delete': False,
                    'export': True,
                },
            },
        )
        profile = self.user.profile
        profile.permission_group = self.group
        profile.save(update_fields=['permission_group'])

    def test_module_access_granted(self):
        self.assertTrue(user_can_access_module(self.user, MODULE_KHO_NPL))

    def test_overview_page_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('kho_npl:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tổng quan tồn kho')

    def test_denied_without_view_permission(self):
        self.group.module_permissions = {
            MODULE_KHO_NPL: {
                'view': False,
                'create': False,
                'update': False,
                'delete': False,
                'export': False,
            },
        }
        self.group.save(update_fields=['module_permissions'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('kho_npl:material_list'))
        self.assertEqual(response.status_code, 302)
