from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from reports.report_profile import REPORT_PROFILE_OFFICE


@override_settings(MEDIA_ROOT='/tmp/portal-test-media')
class ReportsCkeditorUploadTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='VP Upload',
            sort_order=1,
            report_profile=REPORT_PROFILE_OFFICE,
        )
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True}}},
        )
        self.user = User.objects.create_user(username='vp_upload', password='test')
        Profile.objects.filter(user=self.user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='VP Upload',
            is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_ckeditor_upload_returns_ckeditor4_json(self):
        upload = SimpleUploadedFile(
            'paste.png',
            b'\x89PNG\r\n\x1a\n',
            content_type='image/png',
        )
        resp = self.client.post(
            reverse('reports:ckeditor5_upload'),
            data={'upload': upload},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['uploaded'], 1)
        self.assertIn('url', data)
        self.assertTrue(data['url'])

    def test_legacy_upload_url_works(self):
        upload = SimpleUploadedFile('x.jpg', b'jpeg', content_type='image/jpeg')
        resp = self.client.post(
            reverse('reports:ckeditor5_upload_legacy'),
            data={'upload': upload},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['uploaded'], 1)

    def test_today_vp_page_includes_upload_url(self):
        resp = self.client.get(reverse('reports:today_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:ckeditor5_upload'))
        self.assertContains(resp, 'JP_REPORTS_CK_UPLOAD_URL')
