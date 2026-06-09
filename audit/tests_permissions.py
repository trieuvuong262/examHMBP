from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_AUDIT
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import (
    MODULE_VIEW_EXPORT_ONLY,
    normalize_group_permissions,
    permissions_from_legacy_role,
)


class AuditPermissionMatrixTests(TestCase):
    def test_audit_module_is_view_export_only(self):
        self.assertIn('audit', MODULE_VIEW_EXPORT_ONLY)

    def test_legacy_edit_maps_to_view_and_export_only(self):
        perms = normalize_group_permissions({
            'audit': {'view': True, 'edit': True},
        })
        audit = perms['audit']
        self.assertTrue(audit['view'])
        self.assertTrue(audit['export'])
        self.assertFalse(audit['create'])
        self.assertFalse(audit['update'])
        self.assertFalse(audit['delete'])


class AuditGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Audit Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['audit'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_AUDIT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-audit-view',
            name='Audit view only',
            module_permissions=view_only,
        )

        exporter = dict(base)
        exporter[MODULE_AUDIT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': True,
        }
        self.group_export = PermissionGroup.objects.create(
            slug='test-audit-export',
            name='Audit export',
            module_permissions=exporter,
        )

        self.view_user = User.objects.create_user(username='audit_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.export_user = User.objects.create_user(username='audit_export', password='testpass123')
        Profile.objects.filter(user=self.export_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_export,
        )

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_open_log_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('audit:log_list'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_export_logs(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('audit:log_export_excel'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_export_user_can_export_logs(self):
        self.client.force_login(self.export_user)
        response = self.client.get(reverse('audit:log_export_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_view_only_cannot_run_backup(self):
        self.client.force_login(self.view_user)
        response = self.client.post(reverse('audit:backup_run'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
