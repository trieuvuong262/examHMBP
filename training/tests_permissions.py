from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_TRAINING
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
from training.models import Course


class TrainingGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Training Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['training'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_TRAINING] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-training-view',
            name='Training view only',
            module_permissions=view_only,
        )

        editor = dict(base)
        editor[MODULE_TRAINING] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_editor = PermissionGroup.objects.create(
            slug='test-training-editor',
            name='Training editor',
            module_permissions=editor,
        )

        self.view_user = User.objects.create_user(username='train_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.editor_user = User.objects.create_user(username='train_editor', password='testpass123')
        Profile.objects.filter(user=self.editor_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_editor,
        )

        self.course = Course.objects.create(
            title='Test course',
            description='Desc',
            is_active=True,
        )
        self.course.assigned_users.add(self.view_user)

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_open_my_courses(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('my_courses'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_course_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('course_list'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_course_list(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('course_list'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_create_course(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('course_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_create_course(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('course_create'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_edit_course(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('course_edit', args=[self.course.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
