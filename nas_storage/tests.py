import json
import os
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, Profile
from hrm.module_permissions import MODULE_NAS_STORAGE, resolve_module_from_request
from nas_storage.models import NasShareLink
from nas_storage.models import NasUserFolderAccess
from nas_storage.nas_paths import (
    NasPathError,
    department_default_nas_roots,
    department_folder_code,
    get_user_nas_roots,
    list_directory_via_rclone,
    normalize_rel_path,
    resolve_nas_path,
)
from nas_storage.user_folders import user_has_custom_nas_folders
from nas_storage.share_access import get_active_share, is_path_under_share


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

    def test_custom_nas_roots_override_department_defaults(self):
        NasUserFolderAccess.objects.create(
            user=self.user,
            label='Dự án A',
            rel_path='IT/du-an-a',
            sort_order=0,
        )
        self.assertTrue(user_has_custom_nas_folders(self.user))
        roots = get_user_nas_roots(self.user)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0].rel_path, 'IT/du-an-a')
        import os
        os.makedirs('/tmp/nas-test/IT/du-an-a', exist_ok=True)
        path = resolve_nas_path(self.user, 'IT/du-an-a')
        self.assertTrue(str(path).endswith('IT/du-an-a'))

    def test_department_default_roots_helper(self):
        defaults = department_default_nas_roots(self.user)
        self.assertEqual(len(defaults), 2)

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
        with patch('nas_storage.views.list_directory_with_source', return_value=(listing, 'rclone', False)):
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
        with patch('nas_storage.views.list_directory_with_source', return_value=(listing, 'rclone', False)):
            url = reverse('nas_storage:sync') + '?path=IT/VuongIT'
            response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('html', data)
        self.assertEqual(data['folder_count'], 1)
        self.assertIn('docs', data['html'])
        self.assertIn('listing_key', data)
        self.assertIn('source', data)
        self.assertTrue(data.get('ok'))


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

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-rclone-pref-test', NAS_RCLONE_CONFIG='/tmp/fake-rclone.conf')
    def test_list_directory_prefers_rclone(self):
        import nas_storage.nas_paths as np
        np._rclone_listing_ok = None
        os.makedirs('/tmp/nas-rclone-pref-test/IT/u', exist_ok=True)
        listing = {'folders': [], 'files': [{'name': 'live.txt', 'size': 1, 'modified': 0, 'is_dir': False}]}
        with patch.object(np, 'rclone_listing_available', return_value=True):
            with patch.object(np, 'list_directory_via_rclone', return_value=listing):
                result, source, stale = np.list_directory_with_source(
                    np.nas_mount_root() / 'IT/u', fresh=True, rel_path='IT/u',
                )
        self.assertEqual(source, 'rclone')
        self.assertFalse(stale)
        self.assertEqual(result['files'][0]['name'], 'live.txt')


class NasShareTests(TestCase):
    def setUp(self):
        self.dept_a = Department.objects.create(name='IT', sort_order=1)
        self.dept_b = Department.objects.create(name='HÀNH CHÍNH NHÂN SỰ', sort_order=2)
        self.owner = User.objects.create_user(username='ownerIT', password='test')
        self.recipient = User.objects.create_user(username='hcnsUser', password='test')
        Profile.objects.create(user=self.owner, full_name='Owner', department=self.dept_a)
        Profile.objects.create(user=self.recipient, full_name='Recipient', department=self.dept_b)

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-share-test')
    def test_create_share_returns_link(self):
        import os
        os.makedirs('/tmp/nas-share-test/IT/ownerIT', exist_ok=True)
        open('/tmp/nas-share-test/IT/ownerIT/report.pdf', 'wb').write(b'data')
        self.client.login(username='ownerIT', password='test')
        response = self.client.post(
            reverse('nas_storage:share_create'),
            {'path': 'IT/ownerIT/report.pdf'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('/chia-se/', data['url'])
        self.assertEqual(NasShareLink.objects.count(), 1)

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-share-test')
    def test_recipient_can_open_shared_file(self):
        import os
        os.makedirs('/tmp/nas-share-test/IT/ownerIT', exist_ok=True)
        open('/tmp/nas-share-test/IT/ownerIT/report.pdf', 'wb').write(b'data')
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/report.pdf',
            item_name='report.pdf',
            is_dir=False,
            expires_at=NasShareLink.default_expiry(),
        )
        self.client.login(username='hcnsUser', password='test')
        response = self.client.get(reverse('nas_storage:share_open', args=[share.token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'report.pdf')

    def test_is_path_under_share(self):
        self.assertTrue(is_path_under_share('IT/ownerIT/docs', 'IT/ownerIT'))
        self.assertFalse(is_path_under_share('IT/other/file', 'IT/ownerIT'))

    def test_expired_share_is_invalid(self):
        from django.utils import timezone
        from datetime import timedelta
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/a.txt',
            item_name='a.txt',
            is_dir=False,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertIsNone(get_active_share(str(share.token)))

    def test_share_open_requires_login(self):
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/a.txt',
            item_name='a.txt',
            is_dir=False,
            expires_at=NasShareLink.default_expiry(),
        )
        response = self.client.get(reverse('nas_storage:share_open', args=[share.token]))
        self.assertEqual(response.status_code, 302)
