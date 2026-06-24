from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audit.services.nas_monitor import (
    _collect_shares,
    _volume_from_storage_api,
    collect_dsm_widgets,
    collect_nas_metrics,
    dsm_configured,
)
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_AUDIT


class NasMonitorServiceTests(TestCase):
    @patch('audit.services.nas_monitor.rclone_listing_available', return_value=False)
    @patch('audit.services.nas_monitor.nas_is_available', return_value=False)
    def test_collect_metrics_without_rclone(self, *_mocks):
        metrics = collect_nas_metrics()
        self.assertIn('ram', metrics)
        self.assertIn('cpu', metrics)
        self.assertIn('shares', metrics)
        self.assertIn('processes', metrics)
        self.assertFalse(metrics['dsm_available'])

    @override_settings(NAS_DSM_URL='', NAS_DSM_ACCOUNT='', NAS_DSM_PASSWORD='')
    @patch('audit.services.nas_monitor._read_nas_cred', return_value=('', ''))
    def test_dsm_not_configured(self, _mock):
        self.assertFalse(dsm_configured())

    @override_settings(NAS_DSM_URL='https://nas.example:5001', NAS_DSM_PASSWORD='')
    @patch('audit.services.nas_monitor._read_nas_cred', return_value=('tailscale-justplay', 'secret'))
    def test_dsm_configured_from_cred_file(self, _mock):
        self.assertTrue(dsm_configured())

    @override_settings(
        NAS_DSM_URL='https://nas.example:5001',
        NAS_DSM_ACCOUNT='tailscale-justplay',
        NAS_DSM_PASSWORD='secret',
    )
    def test_dsm_configured_from_env(self):
        self.assertTrue(dsm_configured())

    def test_volume_from_storage_api(self):
        row = _volume_from_storage_api({
            'display_name': 'Volume 1',
            'volume_path': '/volume1',
            'size_total_byte': '1000',
            'size_free_byte': '400',
            'status': 'normal',
            'volume_id': 1,
        })
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row['used_bytes'], 600)
        self.assertEqual(row['vol_path'], '/volume1')

    @patch('audit.services.nas_monitor._dsm_request')
    def test_utilization_memory_in_kilobytes(self, mock_dsm):
        from audit.services.nas_monitor import _read_dsm_utilization

        mock_dsm.return_value = {
            'cpu': {'load': 12},
            'memory': {
                'total_real': 8388608,
                'avail_real': 4194304,
                'real_usage': 50,
            },
        }
        util = _read_dsm_utilization()
        self.assertEqual(util['ram']['total_bytes'], 8388608 * 1024)
        self.assertEqual(util['ram']['used_bytes'], 4194304 * 1024)
        self.assertEqual(util['ram']['used_percent'], 50)
        self.assertIn('GB', util['ram']['display'])

    @patch('audit.services.nas_monitor._read_dsm_filestation_shares', return_value=[])
    @patch('audit.services.nas_monitor._list_shares_from_rclone')
    @patch('audit.services.nas_monitor._read_dsm_volumes')
    def test_collect_shares_fallback_rclone(self, mock_vols, mock_rclone, _mock_fs):
        mock_vols.return_value = []
        mock_rclone.return_value = [{'name': 'backup', 'display': '—'}]
        rows = _collect_shares(volumes=[])
        self.assertEqual(rows[0]['name'], 'backup')

    @override_settings(NAS_DSM_URL='', NAS_DSM_PASSWORD='')
    @patch('audit.services.nas_monitor._read_nas_cred', return_value=('', ''))
    def test_collect_dsm_widgets_empty_without_dsm(self, _mock):
        self.assertEqual(collect_dsm_widgets(), {})


class NasMonitorViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT DL', sort_order=1)
        DepartmentMenuPermission.objects.create(department=cls.dept, modules=['audit'])
        cls.group = PermissionGroup.objects.create(
            name='IT NAS',
            slug='it-nas-test',
            module_permissions={
                MODULE_AUDIT: {
                    'view': True,
                    'menus': {
                        'nas_monitor': {
                            'view': True,
                        },
                    },
                },
            },
        )
        cls.user = User.objects.create_user(username='nasadmin', password='pass12345')
        profile = Profile.objects.get(user=cls.user)
        profile.department = cls.dept
        profile.permission_group = cls.group
        profile.save()

    def setUp(self):
        self.client = Client()
        self.client.login(username='nasadmin', password='pass12345')

    def test_page_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('audit:nas_monitor'))
        self.assertEqual(resp.status_code, 302)

    def test_page_loads(self):
        resp = self.client.get(reverse('audit:nas_monitor'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Giám sát NAS')
        self.assertContains(resp, 'Performance')
        self.assertContains(resp, 'jp-nas-tab-performance')
        self.assertContains(resp, 'Hệ thống DSM')

    @patch('audit.views_nas.collect_nas_metrics')
    def test_metrics_api(self, mock_collect):
        mock_collect.return_value = {'ram': {}, 'cpu': {}, 'disk': None, 'shares': []}
        resp = self.client.get(reverse('audit:nas_monitor_metrics'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
