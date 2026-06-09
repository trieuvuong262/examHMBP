from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_RECRUITMENT
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class RecruitmentGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Recruitment Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['recruitment'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_RECRUITMENT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-recruitment-view',
            name='Recruitment view only',
            module_permissions=view_only,
        )

        export_only = dict(base)
        export_only[MODULE_RECRUITMENT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': True,
        }
        self.group_export = PermissionGroup.objects.create(
            slug='test-recruitment-export',
            name='Recruitment export',
            module_permissions=export_only,
        )

        self.view_user = User.objects.create_user(username='rec_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.export_user = User.objects.create_user(username='rec_export', password='testpass123')
        Profile.objects.filter(user=self.export_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_export,
        )

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_open_kanban(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('kanban_board'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_export_interviews(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('export_interviews_excel'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_export_user_can_export_interviews(self):
        self.client.force_login(self.export_user)
        response = self.client.get(reverse('export_interviews_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_view_only_cannot_add_job_posting(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('job_posting_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
