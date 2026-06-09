from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from announcements.models import Announcement
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_ANNOUNCEMENTS
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class AnnouncementGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Announcements Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['announcements'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_ANNOUNCEMENTS] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-announcements-view',
            name='Announcements view only',
            module_permissions=view_only,
        )

        editor = dict(base)
        editor[MODULE_ANNOUNCEMENTS] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_editor = PermissionGroup.objects.create(
            slug='test-announcements-editor',
            name='Announcements editor',
            module_permissions=editor,
        )

        self.view_user = User.objects.create_user(username='ann_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.editor_user = User.objects.create_user(username='ann_editor', password='testpass123')
        Profile.objects.filter(user=self.editor_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_editor,
        )

        self.announcement = Announcement.objects.create(
            title='Test announcement',
            summary='Summary',
            body='Body',
            created_by=self.editor_user,
            is_active=True,
        )

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_open_public_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('announcements:list'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_admin_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('announcements:admin_list'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_admin_list(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('announcements:admin_list'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_create_announcement(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('announcements:admin_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_create_form(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('announcements:admin_create'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_edit_announcement(self):
        self.client.force_login(self.view_user)
        response = self.client.get(
            reverse('announcements:admin_edit', args=[self.announcement.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
