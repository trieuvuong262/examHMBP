from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from hrm.models import Profile
from hrm.module_permissions import MODULE_AUDIT
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE
from kiotviet.models import KvSyncConfig, KvSyncJob
from kiotviet.sync_service import ENTITY_ALL


@override_settings(
    KIOTVIET_ENABLED=True,
    KIOTVIET_RETAILER='testshop',
    KIOTVIET_CLIENT_ID='id',
    KIOTVIET_CLIENT_SECRET='secret',
)
class KiotVietSyncAdminTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(username='kv_sync_dir', password='testpass123')
        profile = Profile.objects.get(user=self.director)
        profile.role = ROLE_DIRECTOR
        profile.full_name = 'Director'
        profile.save()

        self.employee = User.objects.create_user(username='kv_sync_emp', password='testpass123')
        emp_profile = Profile.objects.get(user=self.employee)
        emp_profile.role = ROLE_EMPLOYEE
        emp_profile.module_permissions = {MODULE_AUDIT: {'view': False, 'edit': False}}
        emp_profile.save()

    def test_sync_page_requires_audit_access(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('audit:kiotviet_sync'))
        self.assertEqual(response.status_code, 302)

    def test_director_can_view_sync_page(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('audit:kiotviet_sync'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Đồng bộ KiotViet')

    def test_save_config_creates_record(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('audit:kiotviet_sync_save'), {
            'interval_minutes': '360',
            'schedule_enabled': 'on',
            'entities': ['products', 'customers'],
        })
        self.assertEqual(response.status_code, 302)
        config = KvSyncConfig.objects.get(retailer='testshop')
        self.assertEqual(config.interval_minutes, 360)
        self.assertTrue(config.schedule_enabled)
        self.assertEqual(config.enabled_entities, ['products', 'customers'])

    @patch('kiotviet.sync_views.start_sync_async')
    def test_manual_sync_starts_job(self, mock_start):
        job = KvSyncJob.objects.create(
            trigger=KvSyncJob.TRIGGER_MANUAL,
            status=KvSyncJob.STATUS_PENDING,
            entities=list(ENTITY_ALL),
        )
        mock_start.return_value = job
        self.client.force_login(self.director)
        response = self.client.post(reverse('audit:kiotviet_sync_run'), {
            'entities': ['products'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'job={job.pk}', response.url)
        mock_start.assert_called_once()

    def test_status_api_returns_progress(self):
        job = KvSyncJob.objects.create(
            trigger=KvSyncJob.TRIGGER_MANUAL,
            status=KvSyncJob.STATUS_RUNNING,
            progress_percent=42,
            current_entity='products',
            entities=['products', 'customers'],
        )
        self.client.force_login(self.director)
        response = self.client.get(reverse('audit:kiotviet_sync_status', args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['progress_percent'], 42)
        self.assertEqual(data['current_entity'], 'products')
        self.assertEqual(data['entity_index'], 1)
        self.assertEqual(data['entity_total'], 2)
