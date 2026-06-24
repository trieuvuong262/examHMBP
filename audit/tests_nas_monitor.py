from unittest.mock import patch
import time

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from audit.services.nas_monitor import (
    _collect_shares,
    _format_dsm_time,
    _parse_byte_value,
    _parse_connected_user,
    _parse_log_row,
    _share_row,
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

    def test_share_row_used_only_display(self):
        row = _share_row(name='backup', total_b=None, used_b=5 * 1024 ** 3)
        self.assertIn('Size:', row['display'])
        self.assertIsNone(row['used_percent'])

    def test_share_row_with_quota(self):
        row = _share_row(name='backup', total_b=10 * 1024 ** 3, used_b=2 * 1024 ** 3)
        self.assertEqual(row['used_percent'], 20.0)
        self.assertEqual(row['free_bytes'], 8 * 1024 ** 3)
        self.assertIn('Quota:', row['display'])

    def test_parse_dsm_share_quota_mb(self):
        from audit.services.nas_monitor import _parse_dsm_share_quota

        quota = _parse_dsm_share_quota({
            'name': 'backup',
            'share_quota_status': 'v2',
            'quota_value': 1048576,
            'share_quota_used': 249736.375,
        })
        self.assertIsNotNone(quota)
        assert quota is not None
        self.assertEqual(quota['quota_size'], 1024 ** 4)
        self.assertAlmostEqual(quota['used_space'] / (1024 ** 3), 243.9, delta=1.0)
        self.assertGreater(quota['free_space'], 750 * 1024 ** 3)

        small = _parse_dsm_share_quota({
            'name': '90_MAU_BIEU_FORM_CHUAN',
            'share_quota_status': 'v2',
            'quota_value': 65536,
            'share_quota_used': 0.03125,
        })
        assert small is not None
        self.assertEqual(small['quota_size'], 64 * 1024 ** 3)
        self.assertLess(small['used_space'], 1024 * 100)

    def test_parse_process_memory_percent_from_mem_kb(self):
        from audit.services.nas_monitor import _parse_process_memory_percent

        mem_bytes, mem_pct = _parse_process_memory_percent({'mem': 19796}, 8 * 1024 ** 3)
        self.assertEqual(mem_bytes, 19796 * 1024)
        self.assertAlmostEqual(mem_pct, 0.2, delta=0.1)

    def test_parse_dsm_cpu_percent_from_load_parts(self):
        from audit.services.nas_monitor import _parse_dsm_cpu_percent

        self.assertEqual(_parse_dsm_cpu_percent({'user_load': 9, 'system_load': 8, 'other_load': 1}), 18.0)
        self.assertEqual(_parse_dsm_cpu_percent({'1min_load': 42}), 42.0)

    @patch('audit.services.nas_monitor._dsm_request')
    def test_filestation_share_ignores_volume_status_and_small_size(self, mock_dsm):
        from audit.services.nas_monitor import _read_dsm_filestation_shares

        mock_dsm.return_value = {
            'shares': [
                {
                    'name': 'backup',
                    'path': '/backup',
                    'additional': {
                        'size': 162,
                        'real_path': '/volume1/backup',
                        'volume_status': {'totalspace': 14 * 1024 ** 4},
                    },
                },
                {
                    'name': 'media',
                    'path': '/media',
                    'additional': {'size': 2 * 1024 ** 3, 'real_path': '/volume1/media'},
                },
            ],
        }
        rows = _read_dsm_filestation_shares({})
        by_name = {row['name']: row for row in rows}
        self.assertIsNone(by_name['backup']['used_bytes'])
        self.assertIsNone(by_name['backup']['total_bytes'])
        self.assertEqual(by_name['media']['used_bytes'], 2 * 1024 ** 3)
        self.assertIsNone(by_name['media']['total_bytes'])

    @patch('audit.services.nas_monitor._rclone_about')
    @patch('audit.services.nas_monitor.rclone_listing_available', return_value=True)
    def test_enrich_share_uses_quota_from_about_not_volume(self, _rclone_ok, mock_about):
        from audit.services.nas_monitor import _enrich_shares_from_rclone

        volume_total = 14 * 1024 ** 4
        mock_about.return_value = {
            'total_bytes': 512 * 1024 ** 3,
            'used_bytes': 130 * 1024 ** 3,
            'used_percent': 25.4,
            'display': '130.0 GB / 512.0 GB',
        }
        rows = _enrich_shares_from_rclone(
            [{'name': 'backup', 'remote': 'synology:backup', 'total_bytes': None, 'used_bytes': None}],
            volumes=[{'total_bytes': volume_total}],
            deadline=time.monotonic() + 30,
        )
        self.assertEqual(rows[0]['total_bytes'], 512 * 1024 ** 3)
        self.assertEqual(rows[0]['used_bytes'], 130 * 1024 ** 3)
        self.assertIn('Quota:', rows[0]['display'])

    @patch('audit.services.nas_monitor._rclone_size')
    @patch('audit.services.nas_monitor._rclone_about')
    @patch('audit.services.nas_monitor.rclone_listing_available', return_value=True)
    def test_enrich_share_without_quota_uses_size_only(self, _rclone_ok, mock_about, mock_size):
        from audit.services.nas_monitor import _enrich_shares_from_rclone

        volume_total = 14 * 1024 ** 4
        mock_about.return_value = {
            'total_bytes': volume_total,
            'used_bytes': 5 * 1024 ** 4,
            'used_percent': 35.0,
            'display': '5.0 TB / 14.0 TB',
        }
        mock_size.return_value = 80 * 1024 ** 3
        rows = _enrich_shares_from_rclone(
            [{'name': 'docker', 'remote': 'synology:docker', 'total_bytes': None, 'used_bytes': None}],
            volumes=[{'total_bytes': volume_total}],
            deadline=time.monotonic() + 30,
        )
        self.assertIsNone(rows[0]['total_bytes'])
        self.assertEqual(rows[0]['used_bytes'], 80 * 1024 ** 3)
        self.assertIn('Size:', rows[0]['display'])
        mock_size.assert_called_once()

    def test_parse_byte_value_nested(self):
        self.assertEqual(_parse_byte_value({'size': 4096}), 4096)
        self.assertEqual(_parse_byte_value({'used_space': 1024}), 1024)

    @patch('audit.services.nas_monitor._dsm_request')
    def test_utilization_memory_uses_memory_size_and_real_usage(self, mock_dsm):
        from audit.services.nas_monitor import _read_dsm_utilization

        mock_dsm.return_value = {
            'cpu': {'load': 12},
            'memory': {
                'memory_size': 8388608,
                'total_real': 7923712,
                'avail_real': 4194304,
                'real_usage': 50,
            },
        }
        util = _read_dsm_utilization()
        self.assertEqual(util['ram']['total_bytes'], 8388608 * 1024)
        self.assertEqual(util['ram']['used_bytes'], int(8388608 * 1024 * 0.5))
        self.assertEqual(util['ram']['used_percent'], 50)
        self.assertIn('GB', util['ram']['display'])

    @patch('audit.services.nas_monitor._dsm_request')
    def test_utilization_memory_fallback_total_real(self, mock_dsm):
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
        self.assertEqual(util['ram']['used_percent'], 50)

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

    def test_format_dsm_time_unix(self):
        ts = 1_700_000_000
        formatted = _format_dsm_time(ts)
        self.assertRegex(formatted, r'^\d{4}-\d{2}-\d{2}')

    def test_parse_connected_user_synology_fields(self):
        row = _parse_connected_user({
            'who': 'admin',
            'from': '100.64.0.5',
            'description': 'SMB',
            'connected_time': 1_700_000_000,
        })
        self.assertEqual(row['user'], 'admin')
        self.assertEqual(row['ip'], '100.64.0.5')
        self.assertEqual(row['protocol'], 'SMB')
        self.assertNotEqual(row['time'], '—')

    def test_parse_log_row_fields(self):
        row = _parse_log_row({
            'time': 1_700_000_000,
            'level': 'warn',
            'logtype': 'System',
            'who': 'root',
            'msg': 'disk event',
        })
        self.assertEqual(row['level'], 'warn')
        self.assertEqual(row['source'], 'System')
        self.assertIn('disk event', row['message'])

    @override_settings(
        NAS_DSM_URL='https://nas.example:5556',
        NAS_DSM_ACCOUNT='tailscale-justplay',
        NAS_DSM_PASSWORD='secret',
    )
    @patch('audit.services.nas_monitor._read_dsm_widget_file_changes', return_value=[])
    @patch('audit.services.nas_monitor._read_dsm_widget_backup_tasks', return_value=[])
    @patch('audit.services.nas_monitor._read_dsm_widget_recent_logs', return_value=[])
    @patch('audit.services.nas_monitor._read_dsm_widget_scheduled_tasks', return_value=[])
    @patch('audit.services.nas_monitor._read_dsm_widget_connected_users', return_value=[])
    @patch('audit.services.nas_monitor._read_dsm_widget_system_health')
    @patch('audit.services.nas_monitor._read_dsm_utilization')
    @patch('audit.services.nas_monitor._read_dsm_system_info')
    def test_collect_dsm_widgets_structure(self, mock_info, mock_util, mock_health, *_mocks):
        mock_info.return_value = {'hostname': 'nas', 'uptime_display': '1 ngày'}
        mock_util.return_value = {'cpu_percent': 10, 'ram': {'used_percent': 20}, 'network': []}
        mock_health.return_value = {'status': 'normal', 'items': [], 'disks': []}
        widgets = collect_dsm_widgets(volumes=[{'name': 'vol1'}], shares=[{'name': 'backup'}])
        self.assertIn('system_info', widgets)
        self.assertIn('resource', widgets)
        self.assertIn('storage', widgets)
        self.assertEqual(widgets['storage']['volumes'][0]['name'], 'vol1')
        self.assertEqual(widgets['system_health']['status'], 'normal')


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
        with patch('audit.views_nas.collect_nas_metrics') as mock_collect:
            resp = self.client.get(reverse('audit:nas_monitor'))
        self.assertEqual(resp.status_code, 200)
        mock_collect.assert_not_called()
        self.assertContains(resp, 'Giám sát NAS')
        self.assertContains(resp, 'Performance')
        self.assertContains(resp, 'jp-nas-tab-performance')
        self.assertContains(resp, 'Hệ thống DSM')
        self.assertContains(resp, 'jp-nas-loading')

    @patch('audit.services.nas_monitor._collect_shares')
    @patch('audit.services.nas_monitor.collect_dsm_widgets')
    @patch('audit.services.nas_monitor._read_dsm_volumes', return_value=[{'name': 'vol1', 'total_bytes': 100, 'used_bytes': 50, 'used_percent': 50, 'display': '50 / 100'}])
    @patch('audit.services.nas_monitor._read_dsm_utilization')
    @patch('audit.services.nas_monitor._read_dsm_system_info')
    @patch('audit.services.nas_monitor.dsm_configured', return_value=True)
    @patch('audit.services.nas_monitor.rclone_listing_available', return_value=True)
    def test_collect_metrics_performance_scope_skips_shares_and_widgets(
        self, _rclone, _dsm, mock_info, mock_util, _mock_vols, mock_widgets, mock_shares,
    ):
        mock_info.return_value = {'hostname': 'nas'}
        mock_util.return_value = {'cpu_percent': 5, 'ram': {'used_percent': 10}, 'cpu': {}}
        metrics = collect_nas_metrics(scope='performance')
        self.assertEqual(metrics['scope'], 'performance')
        mock_shares.assert_not_called()
        mock_widgets.assert_not_called()
        self.assertEqual(metrics['shares'], [])

    @patch('audit.views_nas.collect_nas_metrics')
    def test_metrics_api_performance_scope(self, mock_collect):
        mock_collect.return_value = {'ram': {}, 'cpu': {}, 'disk': None, 'shares': [], 'scope': 'performance'}
        resp = self.client.get(reverse('audit:nas_monitor_metrics') + '?scope=performance')
        self.assertEqual(resp.status_code, 200)
        mock_collect.assert_called_once_with(scope='performance')

    @patch('audit.views_nas.collect_nas_metrics')
    def test_metrics_api(self, mock_collect):
        mock_collect.return_value = {'ram': {}, 'cpu': {}, 'disk': None, 'shares': []}
        resp = self.client.get(reverse('audit:nas_monitor_metrics'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
