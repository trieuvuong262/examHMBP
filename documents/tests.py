from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from documents.knowledge_base import build_portal_knowledge
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_DOCUMENTS
from hrm.permissions import ROLE_EMPLOYEE


class LibraryQATests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Test Dept')
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['documents'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    MODULE_DOCUMENTS: {'view': True, 'edit': False},
                },
            },
        )
        self.user = User.objects.create_user(username='libuser', password='pass1234')
        Profile.objects.filter(user=self.user).update(
            full_name='Lib User',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.user = User.objects.select_related('profile', 'profile__department').get(pk=self.user.pk)
        self.client = Client()
        self.client.force_login(self.user)

    def test_qa_page_requires_login(self):
        anon = Client()
        res = anon.get(reverse('documents:qa'))
        self.assertEqual(res.status_code, 302)

    def test_qa_page_loads(self):
        res = self.client.get(reverse('documents:qa'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Hỏi đáp')

    def test_knowledge_includes_user_role(self):
        text = build_portal_knowledge(self.user)
        self.assertIn('Lib User', text)
        self.assertIn('Test Dept', text)

    @patch('documents.views.ask_portal_assistant', return_value='Trả lời mẫu.')
    def test_qa_ask_api(self, mock_ask):
        res = self.client.post(
            reverse('documents:qa_ask'),
            data='{"question":"Xin chào"}',
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['answer'], 'Trả lời mẫu.')
        mock_ask.assert_called_once()
