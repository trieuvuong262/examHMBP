from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from audit.services.vps_monitor import OPTIMIZE_ACTIONS, collect_vps_metrics, run_optimize_action
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_AUDIT


class VpsMonitorServiceTests(TestCase):
    def test_collect_metrics_without_host_mount(self):
        metrics = collect_vps_metrics()
        self.assertIn('ram', metrics)
        self.assertIn('cpu', metrics)
        self.assertIn('disk', metrics)

    def test_invalid_optimize_action(self):
        with self.assertRaises(Exception):
            run_optimize_action('not-real')


class VpsMonitorViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='IT DL', sort_order=1)
        DepartmentMenuPermission.objects.create(department=cls.dept, modules=['audit'])
        cls.group = PermissionGroup.objects.create(
            name='IT VPS',
            slug='it-vps-test',
            module_permissions={
                MODULE_AUDIT: {
                    'view': True,
                    'update': True,
                    'menus': {
                        'vps_monitor': {
                            'view': True,
                            'update': True,
                        },
                    },
                },
            },
        )
        cls.user = User.objects.create_user(username='vpsadmin', password='pass12345')
        profile = Profile.objects.get(user=cls.user)
        profile.department = cls.dept
        profile.permission_group = cls.group
        profile.save()

    def setUp(self):
        self.client = Client()
        self.client.login(username='vpsadmin', password='pass12345')

    def test_page_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('audit:vps_monitor'))
        self.assertEqual(resp.status_code, 302)

    def test_page_loads(self):
        resp = self.client.get(reverse('audit:vps_monitor'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Giám sát VPS')

    @patch('audit.views_vps.collect_vps_metrics')
    def test_metrics_api(self, mock_collect):
        mock_collect.return_value = {'ram': {'used_percent': 20}, 'cpu': {}, 'disk': None, 'docker': {}}
        resp = self.client.get(reverse('audit:vps_monitor_metrics'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')

    @patch('audit.views_vps.run_optimize_action')
    def test_optimize_post(self, mock_run):
        mock_run.return_value = {'message': 'OK'}
        resp = self.client.post(reverse('audit:vps_monitor_optimize'), {'action': 'prune_build_cache'})
        self.assertEqual(resp.status_code, 302)

    def test_optimize_requires_update_perm(self):
        group = PermissionGroup.objects.create(
            name='IT view only',
            slug='it-vps-view',
            module_permissions={
                MODULE_AUDIT: {
                    'view': True,
                    'menus': {'vps_monitor': {'view': True}},
                },
            },
        )
        viewer = User.objects.create_user(username='vpsview', password='pass12345')
        profile = Profile.objects.get(user=viewer)
        profile.department = self.dept
        profile.permission_group = group
        profile.save()
        self.client.login(username='vpsview', password='pass12345')
        with patch('audit.views_vps.run_optimize_action') as mock_run:
            resp = self.client.post(reverse('audit:vps_monitor_optimize'), {'action': 'prune_build_cache'})
            self.assertEqual(resp.status_code, 302)
            mock_run.assert_not_called()

    def test_optimize_actions_registered(self):
        self.assertIn('prune_build_cache', OPTIMIZE_ACTIONS)
        self.assertIn('remove_rembg_volume', OPTIMIZE_ACTIONS)
