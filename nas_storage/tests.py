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
        self.dept, _ = Department.objects.get_or_create(
            name='HÀNH CHÍNH NHÂN SỰ',
            defaults={'sort_order': 1},
        )
        self.user = User.objects.create_user(username='naspath_annt', password='test')
        Profile.objects.filter(user=self.user).update(
            full_name='Test User',
            department=self.dept,
        )

    @override_settings(NAS_DEPT_ROOT_REMOTES='KD-MKT:synology:KD-MKT')
    def test_kd_mkt_department_default_roots_helper(self):
        dept, _ = Department.objects.get_or_create(
            name='KINH DOANH - MARKETING',
            defaults={'sort_order': 2},
        )
        user = User.objects.create_user(username='mkt1', password='test')
        Profile.objects.filter(user=user).update(full_name='MKT', department=dept)
        roots = department_default_nas_roots(user)
        self.assertEqual(roots[0].rel_path, 'mkt1')
        self.assertEqual(roots[1].rel_path, '_CHUNG')

    @override_settings(NAS_DEPT_ROOT_REMOTES='KD-MKT:synology:KD-MKT')
    def test_kd_mkt_user_roots_empty_without_manual_config(self):
        dept, _ = Department.objects.get_or_create(
            name='KINH DOANH - MARKETING',
            defaults={'sort_order': 2},
        )
        user = User.objects.create_user(username='mkt1b', password='test')
        Profile.objects.filter(user=user).update(full_name='MKT', department=dept)
        self.assertEqual(get_user_nas_roots(user), [])

    @override_settings(NAS_DEPT_ROOT_REMOTES='KD-MKT:synology:KD-MKT')
    def test_kd_mkt_rclone_path_not_under_datachung(self):
        from nas_storage.nas_paths import _rclone_remote_path

        dept, _ = Department.objects.get_or_create(
            name='KINH DOANH - MARKETING',
            defaults={'sort_order': 3},
        )
        user = User.objects.create_user(username='mkt2', password='test')
        Profile.objects.filter(user=user).update(full_name='MKT2', department=dept)
        self.assertEqual(_rclone_remote_path('mkt2', user=user), 'synology:KD-MKT/mkt2')
        self.assertEqual(_rclone_remote_path('KD-MKT/mkt2', user=user), 'synology:KD-MKT/mkt2')

    def test_department_folder_code(self):
        self.assertEqual(department_folder_code('HÀNH CHÍNH NHÂN SỰ'), 'HCNS')

    def test_user_roots_empty_without_manual_config(self):
        self.assertEqual(get_user_nas_roots(self.user), [])

    def test_user_roots_with_manual_config(self):
        NasUserFolderAccess.objects.create(
            user=self.user,
            label='Cá nhân',
            rel_path='HCNS/naspath_annt',
            sort_order=0,
        )
        NasUserFolderAccess.objects.create(
            user=self.user,
            label='Chung phòng ban',
            rel_path='HCNS/_CHUNG',
            sort_order=1,
        )
        roots = get_user_nas_roots(self.user)
        self.assertEqual(len(roots), 2)
        self.assertEqual(roots[0].rel_path, 'HCNS/naspath_annt')
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
        self.assertTrue(path.as_posix().endswith('IT/du-an-a'))

    def test_department_default_roots_helper(self):
        defaults = department_default_nas_roots(self.user)
        self.assertEqual(len(defaults), 2)

    def test_normalize_rejects_traversal(self):
        with self.assertRaises(NasPathError):
            normalize_rel_path('HCNS/../IT/secret')

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-test')
    def test_resolve_allowed_path(self):
        import os
        NasUserFolderAccess.objects.create(
            user=self.user,
            label='Cá nhân',
            rel_path='HCNS/naspath_annt',
            sort_order=0,
        )
        os.makedirs('/tmp/nas-test/HCNS/naspath_annt', exist_ok=True)
        path = resolve_nas_path(self.user, 'HCNS/naspath_annt')
        self.assertTrue(path.as_posix().endswith('HCNS/naspath_annt'))

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-test')
    def test_resolve_denies_other_dept(self):
        import os
        NasUserFolderAccess.objects.create(
            user=self.user,
            label='Cá nhân',
            rel_path='HCNS/naspath_annt',
            sort_order=0,
        )
        os.makedirs('/tmp/nas-test/IT/Other', exist_ok=True)
        with self.assertRaises(NasPathError):
            resolve_nas_path(self.user, 'IT/Other')


class NasUserFoldersViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from hrm.models import Department, Profile
        from hrm.permissions import ROLE_EMPLOYEE

        User = get_user_model()
        self.dept = Department.objects.create(name='NAS-FOLDERS-TEST-DEPT', sort_order=99)
        self.admin = User.objects.create_superuser(username='admin', password='x', email='a@test.com')
        self.target = User.objects.create_user(username='nasuser', password='x')
        Profile.objects.filter(user=self.target).update(
            full_name='NAS User',
            department=self.dept,
            role=ROLE_EMPLOYEE,
        )
        self.client.login(username='admin', password='x')

    def test_user_nas_folders_page_renders(self):
        url = reverse('user_nas_folders', args=[self.target.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cập nhật link NAS')
        self.assertContains(response, 'Lưu link NAS')
        self.assertContains(response, 'thêm từng dòng thủ công')
        self.assertNotContains(response, 'mặc định theo phòng ban')
        self.assertNotContains(response, 'Lấy từ mặc định phòng ban')

    def test_user_nas_folders_save_custom_path(self):
        url = reverse('user_nas_folders', args=[self.target.id])
        response = self.client.post(url, {
            'nas_folders-TOTAL_FORMS': '1',
            'nas_folders-INITIAL_FORMS': '0',
            'nas_folders-MIN_NUM_FORMS': '0',
            'nas_folders-MAX_NUM_FORMS': '1000',
            'nas_folders-0-label': 'Du an',
            'nas_folders-0-rel_path': 'IT/du-an-1',
            'nas_folders-0-description': '',
            'nas_folders-0-sort_order': '0',
            'nas_folders-0-is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        roots = get_user_nas_roots(self.target)
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0].rel_path, 'IT/du-an-1')


class NasModuleRegistrationTests(TestCase):
    def test_resolve_module_from_url(self):
        self.assertEqual(resolve_module_from_request('/thu-muc-nas/'), MODULE_NAS_STORAGE)
        self.assertEqual(resolve_module_from_request('/thu-muc-nas/?path=HCNS/Annt'), MODULE_NAS_STORAGE)


class NasBrowseViewTests(TestCase):
    def setUp(self):
        self.dept, _ = Department.objects.get_or_create(name='IT', defaults={'sort_order': 1})
        self.user = User.objects.create_user(username='VuongIT', password='test')
        Profile.objects.filter(user=self.user).update(full_name='Vuong', department=self.dept)
        NasUserFolderAccess.objects.create(
            user=self.user,
            label='Cá nhân',
            rel_path='IT/VuongIT',
            sort_order=0,
        )
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
        self.assertContains(response, 'Tải lại')
        self.assertNotContains(response, 'Tải lên')
        self.assertNotContains(response, 'jp-nas-auto-sync')

    def test_browse_page_has_share_and_download_actions(self):
        import os
        with override_settings(NAS_MOUNT_ROOT='/tmp/nas-browse-share'):
            os.makedirs('/tmp/nas-browse-share/IT/VuongIT', exist_ok=True)
            with open('/tmp/nas-browse-share/IT/VuongIT/doc.pdf', 'wb') as fh:
                fh.write(b'%PDF')
            listing = {
                'folders': [],
                'files': [{'name': 'doc.pdf', 'size': 4, 'modified': 0, 'is_dir': False, 'mime': 'application/pdf'}],
            }
            with patch('nas_storage.views.list_directory_with_source', return_value=(listing, 'mount', False)):
                response = self.client.get(reverse('nas_storage:browse') + '?path=IT/VuongIT')
        self.assertContains(response, 'jp-nas-share-btn')
        self.assertContains(response, 'tai-xuong')
        self.assertContains(response, 'bi-download')


class NasDeleteTests(TestCase):
    def setUp(self):
        self.dept, _ = Department.objects.get_or_create(name='IT', defaults={'sort_order': 1})
        self.user = User.objects.create_user(username='nas_del_user', password='test')
        Profile.objects.filter(user=self.user).update(full_name='Del', department=self.dept)

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-del-test')
    def test_delete_nas_item_uses_rclone_when_missing_on_mount(self):
        from unittest.mock import patch

        from nas_storage.nas_paths import delete_nas_item

        rel = 'IT/nas_del_user/only-on-nas.txt'
        with patch('nas_storage.nas_paths.nas_item_kind', return_value='file'):
            with patch('nas_storage.nas_paths.delete_via_rclone') as mock_del:
                name = delete_nas_item(self.user, rel)
        self.assertEqual(name, 'only-on-nas.txt')
        mock_del.assert_called_once()

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-del-test')
    def test_delete_view_via_rclone_when_not_on_mount(self):
        from unittest.mock import patch

        self.client.login(username='nas_del_user', password='test')
        rel = 'IT/nas_del_user/only-on-nas.txt'
        with patch('nas_storage.views.delete_nas_item', return_value='only-on-nas.txt'):
            response = self.client.post(
                reverse('nas_storage:delete'),
                {'path': rel, 'parent': 'IT/nas_del_user'},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/thu-muc-nas/', response.url)


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
        from hrm.models import DepartmentMenuPermission, PermissionGroup
        from hrm.module_permissions import MODULE_NAS_STORAGE
        from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
        from hrm.permissions import ROLE_EMPLOYEE

        self.dept_a, _ = Department.objects.get_or_create(name='IT', defaults={'sort_order': 1})
        self.dept_b, _ = Department.objects.get_or_create(
            name='HÀNH CHÍNH NHÂN SỰ',
            defaults={'sort_order': 2},
        )
        DepartmentMenuPermission.objects.get_or_create(
            department=self.dept_a,
            defaults={'modules': ['nas_storage']},
        )
        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        nas_full = dict(base)
        nas_full[MODULE_NAS_STORAGE] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': True,
            'export': False,
        }
        self.nas_group = PermissionGroup.objects.create(
            slug='test-nas-share-owner',
            name='NAS share owner',
            module_permissions=nas_full,
        )
        self.owner = User.objects.create_user(username='ownerIT', password='test')
        self.recipient = User.objects.create_user(username='hcnsUser', password='test')
        Profile.objects.update_or_create(
            user=self.owner,
            defaults={
                'full_name': 'Owner',
                'department': self.dept_a,
                'role': ROLE_EMPLOYEE,
                'permission_group': self.nas_group,
            },
        )
        Profile.objects.update_or_create(
            user=self.recipient,
            defaults={'full_name': 'Recipient', 'department': self.dept_b},
        )
        NasUserFolderAccess.objects.create(
            user=self.owner,
            label='Cá nhân',
            rel_path='IT/ownerIT',
            sort_order=0,
        )

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
        open('/tmp/nas-share-test/IT/ownerIT/report.pdf', 'wb').write(b'%PDF-1.4 test')
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/report.pdf',
            item_name='report.pdf',
            is_dir=False,
            expires_at=None,
        )
        self.client.login(username='hcnsUser', password='test')
        response = self.client.get(reverse('nas_storage:share_open', args=[share.token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'report.pdf')
        self.assertContains(response, 'jp-weekly-embed-wrap')
        self.assertContains(response, reverse('nas_storage:preview'))
        self.assertNotContains(response, 'hết hạn')
        self.assertNotContains(response, 'chia sẻ bởi')

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-share-test')
    def test_share_pdf_preview_endpoint(self):
        import os
        os.makedirs('/tmp/nas-share-test/IT/ownerIT', exist_ok=True)
        open('/tmp/nas-share-test/IT/ownerIT/report.pdf', 'wb').write(b'%PDF-1.4 test')
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/report.pdf',
            item_name='report.pdf',
            is_dir=False,
            expires_at=None,
        )
        self.client.login(username='hcnsUser', password='test')
        response = self.client.get(
            reverse('nas_storage:preview'),
            {'path': share.rel_path, 'share': str(share.token)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF', b''.join(response.streaming_content))

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-share-test')
    @patch('nas_storage.file_preview.office_preview_available', return_value=True)
    @patch('nas_storage.views.inline_office_pdf_response')
    def test_share_docx_shows_preview_if_office_ready(self, mock_office_preview, _mock_lo):
        import os
        from django.http import HttpResponse

        os.makedirs('/tmp/nas-share-test/IT/ownerIT', exist_ok=True)
        open('/tmp/nas-share-test/IT/ownerIT/bao-cao.docx', 'wb').write(b'docx')
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/bao-cao.docx',
            item_name='bao-cao.docx',
            is_dir=False,
            expires_at=None,
        )
        mock_office_preview.return_value = HttpResponse(b'%PDF-mock', content_type='application/pdf')
        self.client.login(username='hcnsUser', password='test')
        response = self.client.get(reverse('nas_storage:share_open', args=[share.token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'bao-cao.docx')
        self.assertContains(response, 'jp-weekly-embed-wrap')

        preview_resp = self.client.get(
            reverse('nas_storage:preview'),
            {'path': share.rel_path, 'share': str(share.token)},
        )
        self.assertEqual(preview_resp.status_code, 200)
        mock_office_preview.assert_called_once()

    def test_is_path_under_share(self):
        self.assertTrue(is_path_under_share('IT/ownerIT/docs', 'IT/ownerIT'))
        self.assertFalse(is_path_under_share('IT/other/file', 'IT/ownerIT'))

    def test_expired_share_still_valid_without_expiry(self):
        from django.utils import timezone
        from datetime import timedelta
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/a.txt',
            item_name='a.txt',
            is_dir=False,
            expires_at=None,
        )
        self.assertIsNotNone(get_active_share(str(share.token)))

    def test_legacy_expired_date_ignored_after_clearing_expiry(self):
        from django.utils import timezone
        from datetime import timedelta
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/old.txt',
            item_name='old.txt',
            is_dir=False,
            expires_at=timezone.now() - timedelta(days=1),
        )
        share.expires_at = None
        share.save(update_fields=['expires_at'])
        self.assertIsNotNone(get_active_share(str(share.token)))

    def test_share_open_requires_login(self):
        share = NasShareLink.objects.create(
            created_by=self.owner,
            rel_path='IT/ownerIT/a.txt',
            item_name='a.txt',
            is_dir=False,
            expires_at=None,
        )
        response = self.client.get(reverse('nas_storage:share_open', args=[share.token]))
        self.assertEqual(response.status_code, 302)


class NasGranularPermissionTests(TestCase):
    def setUp(self):
        from hrm.models import DepartmentMenuPermission, PermissionGroup
        from hrm.module_permissions import MODULE_NAS_STORAGE
        from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
        from hrm.permissions import ROLE_EMPLOYEE

        self.dept, _ = Department.objects.get_or_create(
            name='IT',
            defaults={'sort_order': 10},
        )
        DepartmentMenuPermission.objects.get_or_create(
            department=self.dept,
            defaults={'modules': ['nas_storage']},
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_NAS_STORAGE] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-nas-view',
            name='NAS view only',
            module_permissions=view_only,
        )

        create_group = dict(base)
        create_group[MODULE_NAS_STORAGE] = {
            'view': True,
            'create': True,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_create = PermissionGroup.objects.create(
            slug='test-nas-create',
            name='NAS create share',
            module_permissions=create_group,
        )

        self.view_user = User.objects.create_user(username='nas_view_only', password='test')
        Profile.objects.filter(user=self.view_user).update(
            full_name='NAS View',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.create_user = User.objects.create_user(username='nas_create_user', password='test')
        Profile.objects.filter(user=self.create_user).update(
            full_name='NAS Create',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_create,
        )
        for nas_user in (self.view_user, self.create_user):
            NasUserFolderAccess.objects.create(
                user=nas_user,
                label='Cá nhân',
                rel_path=f'IT/{nas_user.username}',
                sort_order=0,
            )

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-granular-test')
    def test_view_only_cannot_create_share(self):
        import os

        os.makedirs('/tmp/nas-granular-test/IT/nas_view_only', exist_ok=True)
        open('/tmp/nas-granular-test/IT/nas_view_only/doc.pdf', 'wb').write(b'data')
        self.client.login(username='nas_view_only', password='test')
        response = self.client.post(
            reverse('nas_storage:share_create'),
            {'path': 'IT/nas_view_only/doc.pdf'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(NasShareLink.objects.count(), 0)

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-granular-create-test')
    def test_create_user_can_create_share(self):
        import os

        os.makedirs('/tmp/nas-granular-create-test/IT/nas_create_user', exist_ok=True)
        open('/tmp/nas-granular-create-test/IT/nas_create_user/doc.pdf', 'wb').write(b'data')
        self.client.login(username='nas_create_user', password='test')
        response = self.client.post(
            reverse('nas_storage:share_create'),
            {'path': 'IT/nas_create_user/doc.pdf'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(NasShareLink.objects.count(), 1)
