from datetime import date
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport
from reports.office_content import (
    prepare_document_html_for_display,
    sanitize_document_html_for_storage,
)
from reports.report_profile import REPORT_PROFILE_OFFICE


class DocumentImageDisplayTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='DocImg Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )
        self.member = self._user('doc_member', ROLE_EMPLOYEE, dept)
        self.leader = self._user('doc_leader', ROLE_TEAM_LEADER, dept)
        self.leader.profile.subordinates.add(self.member)
        self.client = Client(HTTP_HOST='testserver')
        self.report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=dept, role=role, full_name=username, is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_sanitize_strips_ckeditor_widget_wrapper(self):
        raw = (
            '<p>Hi</p>'
            '<span class="cke_widget_wrapper cke_widget_image">'
            '<img src="/media/reports/ckeditor5/abc.png" alt="x" />'
            '</span>'
        )
        cleaned = sanitize_document_html_for_storage(raw)
        self.assertNotIn('cke_widget_wrapper', cleaned)
        self.assertIn('abc.png', cleaned)

    @override_settings(MEDIA_URL='/media/')
    def test_prepare_document_html_rewrites_inline_image_url(self):
        html = '<p>Xem</p><img src="/media/reports/ckeditor5/abc.png" alt="demo">'
        request = self.client.request().wsgi_request
        request.META['HTTP_HOST'] = 'testserver'
        request.META['SERVER_NAME'] = 'testserver'
        request.META['SERVER_PORT'] = '80'
        out = prepare_document_html_for_display(html, self.report, request)
        self.assertIn(reverse('reports:document_image', kwargs={
            'report_pk': self.report.pk,
            'relpath': 'reports/ckeditor5/abc.png',
        }), out)
        self.assertNotIn('/media/reports/ckeditor5/abc.png', out)

    @override_settings(MEDIA_URL='/media/')
    def test_leader_can_load_document_image(self):
        rel = 'reports/ckeditor5/test-doc.png'
        default_storage.save(rel, BytesIO(b'\x89PNG\r\n\x1a\n'))
        self.report.document_html = f'<p><img src="/media/{rel}"></p>'
        self.report.save(update_fields=['document_html'])

        self.client.force_login(self.leader)
        detail = self.client.get(reverse('reports:detail_vp', args=[self.report.pk]))
        self.assertEqual(detail.status_code, 200)
        serve_path = reverse('reports:document_image', kwargs={
            'report_pk': self.report.pk,
            'relpath': rel,
        })
        self.assertContains(detail, serve_path)

        img_resp = self.client.get(serve_path)
        self.assertEqual(img_resp.status_code, 200)
        self.assertEqual(img_resp['Content-Type'], 'image/png')

    def test_outsider_cannot_load_document_image(self):
        rel = 'reports/ckeditor5/private.png'
        default_storage.save(rel, BytesIO(b'\x89PNG\r\n\x1a\n'))
        outsider = self._user('doc_outsider', ROLE_EMPLOYEE, self.member.profile.department)
        self.client.force_login(outsider)
        resp = self.client.get(reverse('reports:document_image', kwargs={
            'report_pk': self.report.pk,
            'relpath': rel,
        }))
        self.assertEqual(resp.status_code, 404)
