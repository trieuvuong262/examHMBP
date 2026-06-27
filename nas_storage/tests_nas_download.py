from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from nas_storage.nas_download_access import user_can_nas_download


class NasDownloadAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('nasuser', password='test')

    @patch('nas_storage.nas_download_access.user_can_access_menu')
    def test_falls_back_to_browse(self, mock_menu):
        mock_menu.side_effect = lambda user, module, menu: menu == 'browse'
        self.assertTrue(user_can_nas_download(self.user))

    @patch('nas_storage.views_nas_download.user_can_nas_download', return_value=True)
    def test_download_page_ok(self, _access):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('nas_storage:nas_download'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Tải bộ cài')
