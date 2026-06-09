from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assessment.models import Exam
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_ASSESSMENT
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class AssessmentGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Assessment Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['assessment'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_ASSESSMENT] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-assessment-view',
            name='Assessment view only',
            module_permissions=view_only,
        )

        editor = dict(base)
        editor[MODULE_ASSESSMENT] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_editor = PermissionGroup.objects.create(
            slug='test-assessment-editor',
            name='Assessment editor',
            module_permissions=editor,
        )

        self.view_user = User.objects.create_user(username='exam_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.editor_user = User.objects.create_user(username='exam_editor', password='testpass123')
        Profile.objects.filter(user=self.editor_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_editor,
        )

        now = timezone.now()
        self.exam = Exam.objects.create(
            title='Test exam',
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            duration_minutes=30,
            is_active=True,
        )
        self.exam.assigned_users.add(self.view_user)

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_open_exam_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('exam_list'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_create_exam(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('exam_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_exam_create(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('exam_create'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_admin_results(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('admin_results'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_admin_results(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('admin_results'))
        self.assertEqual(response.status_code, 200)

    def test_editor_can_open_dashboard_with_assessment_tab(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('admin_dashboard'), {'tab': 'assessment'})
        self.assertEqual(response.status_code, 200)
