from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from documents.models import Document, DocumentCategory
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_DOCUMENTS
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class DocumentsGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Documents Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['documents'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_DOCUMENTS] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-documents-view',
            name='Documents view only',
            module_permissions=view_only,
        )

        editor = dict(base)
        editor[MODULE_DOCUMENTS] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_editor = PermissionGroup.objects.create(
            slug='test-documents-editor',
            name='Documents editor',
            module_permissions=editor,
        )

        self.view_user = User.objects.create_user(username='doc_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.editor_user = User.objects.create_user(username='doc_editor', password='testpass123')
        Profile.objects.filter(user=self.editor_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_editor,
        )

        self.category = DocumentCategory.objects.create(
            name='HR Docs',
            slug='hr-docs',
            is_active=True,
        )
        self.document = Document.objects.create(
            category=self.category,
            title='Policy',
            slug='policy',
            is_active=True,
        )

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_browse_library(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('documents:browse'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_admin_hub(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('documents:admin_hub'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_admin_hub(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('documents:admin_hub'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_create_document(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('documents:admin_document_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_editor_can_open_create_document(self):
        self.client.force_login(self.editor_user)
        response = self.client.get(reverse('documents:admin_document_create'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_edit_document(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('documents:admin_document_edit', args=[self.document.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
