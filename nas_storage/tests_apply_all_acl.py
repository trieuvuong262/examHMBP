from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import (
    NasAclApplyError,
    apply_all_folder_permissions,
    ensure_directory_on_nas,
)


class EnsureDirectoryOnNasTests(TestCase):
    def test_invalid_path_raises_acl_error_not_name_error(self):
        with self.assertRaises(NasAclApplyError):
            ensure_directory_on_nas('../etc/passwd')

    @patch('nas_storage.nas_acl_apply._run_ssh_commands', return_value='OK')
    def test_relative_path_uses_share_name(self, mock_run):
        ensure_directory_on_nas('KD-MKT/_CHUNG', share_name='07_SAN_XUAT')
        mock_run.assert_called_once()


@override_settings(
    NAS_SSH_HOST='nas.test',
    NAS_SSH_ADMIN_USER='admin',
    NAS_SSH_ADMIN_PASSWORD='secret',
)
class ApplyAllFolderPermissionsTests(TestCase):
    def setUp(self):
        NasShareFolder.objects.create(
            share_name='00_QUY_DINH_CHUNG',
            volume_path='/volume1/00_QUY_DINH_CHUNG',
        )

    @patch('nas_storage.nas_acl_apply.apply_folder_permissions', return_value={'status': 'ok'})
    def test_reuses_single_ssh_session(self, mock_apply):
        fake_client = MagicMock()
        fake_paramiko = MagicMock()
        fake_paramiko.SSHClient.return_value = fake_client
        fake_paramiko.AutoAddPolicy.return_value = MagicMock()

        with patch.dict('sys.modules', {'paramiko': fake_paramiko}):
            stats = apply_all_folder_permissions()

        fake_client.connect.assert_called_once()
        fake_client.close.assert_called_once()
        mock_apply.assert_called_once()
        self.assertIs(mock_apply.call_args.kwargs.get('client'), fake_client)
        self.assertEqual(stats['ok'], 1)


class ApplyAllAclViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('nasadmin', password='test')
        self.client.login(username='nasadmin', password='test')

    @patch('nas_storage.views_permissions.user_can_update_menu', return_value=True)
    @patch('nas_storage.views_permissions.apply_all_folder_permissions')
    @patch('nas_storage.views_permissions.sync_browse_all_share_permissions')
    def test_post_redirects_with_success(self, mock_sync, mock_apply, _perm):
        mock_apply.return_value = {'ok': 2, 'skipped': 0, 'errors': []}
        response = self.client.post(reverse('nas_storage:apply_all_acl'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('nas_storage:permissions_hub'))
        mock_sync.assert_called_once()
        mock_apply.assert_called_once()

    @patch('nas_storage.views_permissions.user_can_update_menu', return_value=True)
    @patch('nas_storage.views_permissions.apply_all_folder_permissions')
    @patch('nas_storage.views_permissions.sync_browse_all_share_permissions')
    def test_unexpected_error_returns_redirect_not_500(self, mock_sync, mock_apply, _perm):
        mock_apply.side_effect = RuntimeError('boom')
        response = self.client.post(reverse('nas_storage:apply_all_acl'))
        self.assertEqual(response.status_code, 302)
