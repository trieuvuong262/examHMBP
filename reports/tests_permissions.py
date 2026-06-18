from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class ReportsGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Reports Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['reports'])

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_REPORTS] = {
            'view': True, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-reports-view',
            name='Reports view only',
            module_permissions=view_only,
        )

        submitter = dict(base)
        submitter[MODULE_REPORTS] = {
            'view': True, 'create': True, 'update': False, 'delete': False, 'export': False,
        }
        self.group_submit = PermissionGroup.objects.create(
            slug='test-reports-submit',
            name='Reports submit',
            module_permissions=submitter,
        )

        self.view_user = self._user('rep_view', ROLE_EMPLOYEE, self.group_view)
        self.submit_user = self._user('rep_submit', ROLE_EMPLOYEE, self.group_submit)
        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, role, group):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=role,
            permission_group=group,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_view_only_can_open_hub(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('reports:hub'))
        self.assertEqual(response.status_code, 302)

    def test_view_only_cannot_open_today_report(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('reports:today'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_submit_user_can_open_today_report(self):
        self.client.force_login(self.submit_user)
        response = self.client.get(reverse('reports:today_cn'))
        self.assertEqual(response.status_code, 200)
