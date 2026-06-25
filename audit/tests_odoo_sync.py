from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audit.services.odoo_sync import (
    odoo_configured,
    sync_user_to_odoo,
    user_has_odoo_portal_access,
)
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_ODOO


@override_settings(
    ODOO_URL='https://erp.example.com',
    ODOO_DB='test_db',
    ODOO_API_USER='admin',
    ODOO_API_PASSWORD='secret',
)
class OdooSyncServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT Odoo Test', sort_order=1)
        DepartmentMenuPermission.objects.create(department=cls.dept, modules=['odoo'])
        cls.group = PermissionGroup.objects.create(
            name='IT Odoo',
            slug='it-odoo-test',
            module_permissions={
                MODULE_ODOO: {
                    'view': True,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                },
            },
        )
        cls.user = User.objects.create_user(username='odoouser', password='pass12345', email='odoo@test.local')
        profile = Profile.objects.get(user=cls.user)
        profile.department = cls.dept
        profile.permission_group = cls.group
        profile.full_name = 'Odoo User'
        profile.is_employed = True
        profile.save()
        cls.user = User.objects.select_related('profile__permission_group').get(pk=cls.user.pk)

    def test_odoo_configured(self):
        self.assertTrue(odoo_configured())

    def test_user_has_odoo_portal_access(self):
        self.assertTrue(user_has_odoo_portal_access(self.user))

    @patch('audit.services.odoo_sync._execute')
    @patch('audit.services.odoo_sync._odoo_uid', return_value=1)
    @patch('audit.services.odoo_sync._group_ids_for_user', return_value=[10])
    def test_sync_user_create(self, _groups, _uid, mock_execute):
        mock_execute.side_effect = [
            [],  # search by login
            42,  # create
        ]
        result = sync_user_to_odoo(self.user)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['odoo_user_id'], 42)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.odoo_user_id, 42)


class OdooRedirectViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT2', sort_order=2)
        DepartmentMenuPermission.objects.create(department=cls.dept, modules=['odoo'])
        cls.group = PermissionGroup.objects.create(
            name='IT Odoo view',
            slug='it-odoo-view',
            module_permissions={
                MODULE_ODOO: {
                    'view': True,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                },
            },
        )
        cls.user = User.objects.create_user(username='odooview', password='pass12345')
        profile = Profile.objects.get(user=cls.user)
        profile.department = cls.dept
        profile.permission_group = cls.group
        profile.is_employed = True
        profile.save()

        cls.denied = User.objects.create_user(username='noodoo', password='pass12345')
        denied_profile = Profile.objects.get(user=cls.denied)
        denied_profile.department = cls.dept
        denied_profile.is_employed = True
        denied_profile.save()

        cls.user = User.objects.select_related('profile__permission_group').get(pk=cls.user.pk)
        cls.denied = User.objects.select_related('profile').get(pk=cls.denied.pk)

    def setUp(self):
        self.client = Client()

    def test_redirect_requires_odoo_module_perm(self):
        self.client.login(username='noodoo', password='pass12345')
        resp = self.client.get(reverse('odoo:redirect'))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('erp', resp['Location'].lower())

    @patch('audit.views_odoo.ensure_portal_user_in_odoo', return_value={'status': 'ok'})
    def test_redirect_allowed(self, _mock):
        self.client.login(username='odooview', password='pass12345')
        resp = self.client.get(reverse('odoo:redirect'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('erp', resp['Location'].lower())
