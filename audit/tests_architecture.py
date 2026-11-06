from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .architecture_service import build_architecture_map


class ArchitectureMapAccessTests(TestCase):
    def setUp(self):
        self.url = reverse('audit:architecture_map')
        self.user = User.objects.create_user(username='architecture-user', password='pass')
        self.superuser = User.objects.create_superuser(
            username='architecture-admin',
            password='pass',
            email='architecture@example.test',
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_non_superuser_gets_forbidden(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view_architecture_metadata(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.url, {'app': 'san_xuat'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quản lý code')
        self.assertContains(response, 'post_gc_progress')
        self.assertContains(response, 'san_xuat')
        self.assertNotContains(response, 'SECRET_KEY')
        self.assertNotContains(response, 'DB_PASSWORD')

    def test_service_returns_filtered_models_and_static_limitations(self):
        data = build_architecture_map('kho_npl')
        self.assertTrue(data['models'])
        self.assertTrue(all(model['app'] == 'kho_npl' for model in data['models']))
        self.assertTrue(data['meta']['static_analysis'])
        self.assertTrue(data['meta']['limitations'])
