import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, Profile
from hrm.module_permissions import MODULE_NAS_STORAGE, resolve_module_from_request
from nas_storage.nas_paths import (
    NasPathError,
    department_folder_code,
    get_user_nas_roots,
    list_directory_via_rclone,
    normalize_rel_path,
    resolve_nas_path,
)


class NasPathTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='HÀNH CHÍNH NHÂN SỰ', sort_order=1)
        self.user = User.objects.create_user(username='Annt', password='test')
        Profile.objects.create(user=self.user, full_name='Test User', department=self.dept)

    def test_department_folder_code(self):
        self.assertEqual(department_folder_code('HÀNH CHÍNH NHÂN SỰ'), 'HCNS')

    def test_user_roots(self):
        roots = get_user_nas_roots(self.user)
        self.assertEqual(len(roots), 2)
        self.assertEqual(roots[0].rel_path, 'HCNS/Annt')
        self.assertEqual(roots[1].rel_path, 'HCNS/_CHUNG')

    def test_normalize_rejects_traversal(self):
        with self.assertRaises(NasPathError):
            normalize_rel_path('HCNS/../IT/secret')

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-test')
    def test_resolve_allowed_path(self):
        import os
        os.makedirs('/tmp/nas-test/HCNS/Annt', exist_ok=True)
        path = resolve_nas_path(self.user, 'HCNS/Annt')
        self.assertTrue(str(path).endswith('HCNS/Annt'))

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-test')
    def test_resolve_denies_other_dept(self):
        import os
        os.makedirs('/tmp/nas-test/IT/Other', exist_ok=True)
        with self.assertRaises(NasPathError):
            resolve_nas_path(self.user, 'IT/Other')


class NasModuleRegistrationTests(TestCase):
    def test_resolve_module_from_url(self):
        self.assertEqual(resolve_module_from_request('/thu-muc-nas/'), MODULE_NAS_STORAGE)
        self.assertEqual(resolve_module_from_request('/thu-muc-nas/?path=HCNS/Annt'), MODULE_NAS_STORAGE)


class NasBrowseViewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='IT', sort_order=1)
        self.user = User.objects.create_user(username='VuongIT', password='test')
        Profile.objects.create(user=self.user, full_name='Vuong', department=self.dept)
        self.client.login(username='VuongIT', password='test')

    def test_browse_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('nas_storage:browse'))
        self.assertEqual(response.status_code, 302)

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-browse-test')
    def test_browse_with_refresh_flag(self):
        import os
        os.makedirs('/tmp/nas-browse-test/IT/VuongIT', exist_ok=True)
        listing = {'folders': [], 'files': [{'name': 'a.txt', 'size': 1, 'modified': 0, 'is_dir': False, 'mime': 'text/plain'}]}
        with patch('nas_storage.views.list_directory', return_value=listing):
            url = reverse('nas_storage:browse') + '?path=IT/VuongIT&refresh=1'
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'a.txt')
        self.assertContains(response, 'jp-nas-reload-btn')

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-browse-test')
    def test_sync_list_returns_json(self):
        import os
        os.makedirs('/tmp/nas-browse-test/IT/VuongIT', exist_ok=True)
        listing = {'folders': [{'name': 'docs', 'size': 0, 'modified': 0, 'is_dir': True}], 'files': []}
        with patch('nas_storage.views.list_directory', return_value=listing):
            url = reverse('nas_storage:sync') + '?path=IT/VuongIT'
            response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('html', data)
        self.assertEqual(data['folder_count'], 1)
        self.assertIn('docs', data['html'])


class NasRcloneListingTests(TestCase):
    @override_settings(NAS_RCLONE_REMOTE='synology:DATACHUNG')
    def test_list_directory_via_rclone_parses_json(self):
        payload = json.dumps([
            {'Name': 'report.pdf', 'Size': 2048, 'IsDir': False, 'ModTime': '2026-05-28T10:00:00Z'},
            {'Name': 'archive', 'Size': 0, 'IsDir': True},
        ])
        proc = type('Proc', (), {'returncode': 0, 'stdout': payload, 'stderr': ''})()
        with patch('nas_storage.nas_paths.subprocess.run', return_value=proc):
            result = list_directory_via_rclone('IT/VuongIT')
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(result['files'][0]['name'], 'report.pdf')
        self.assertEqual(len(result['folders']), 1)
        self.assertEqual(result['folders'][0]['name'], 'archive')
