import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Model3D

HTML = b'<!DOCTYPE html><html><head><title>t</title></head><body><script type="module">localStorage.getItem("x")</script></body></html>'


class XayDungFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media, AV_SCAN_ENABLED=False)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # username 'admin' = tài khoản hệ thống, bỏ qua phân quyền phòng ban.
        self.admin = get_user_model().objects.create_user(username='admin', password='pw-Strong-123')
        self.client.force_login(self.admin)

    def _upload(self, name='nha.html', content=HTML):
        return self.client.post(reverse('xay_dung:create'), {
            'title': 'Nhà xưởng D5',
            'description': '',
            'html_file': SimpleUploadedFile(name, content, content_type='text/html'),
        })

    def test_upload_and_view(self):
        resp = self._upload()
        obj = Model3D.objects.get()
        self.assertRedirects(resp, reverse('xay_dung:detail', args=[obj.pk]))
        self.assertEqual(obj.original_name, 'nha.html')

        detail = self.client.get(reverse('xay_dung:detail', args=[obj.pk]))
        self.assertContains(detail, 'sandbox="allow-scripts')
        self.assertNotContains(detail, 'allow-same-origin')

        raw = self.client.get(reverse('xay_dung:raw', args=[obj.pk]))
        self.assertEqual(raw.status_code, 200)
        csp = raw['Content-Security-Policy']
        self.assertTrue(csp.startswith('sandbox allow-scripts'))
        self.assertNotIn('allow-same-origin', csp)
        body = raw.content
        self.assertLess(body.index(b'<head>'), body.index(b'localStorage","sessionStorage'))

    def test_rejects_non_html(self):
        resp = self._upload(name='virus.exe', content=b'MZ\x00\x00')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Model3D.objects.exists())

    def test_anonymous_cannot_view_raw(self):
        self._upload()
        obj = Model3D.objects.get()
        self.client.logout()
        raw = self.client.get(reverse('xay_dung:raw', args=[obj.pk]))
        self.assertNotEqual(raw.status_code, 200)

    def test_delete(self):
        self._upload()
        obj = Model3D.objects.get()
        self.client.post(reverse('xay_dung:delete', args=[obj.pk]))
        self.assertFalse(Model3D.objects.exists())
