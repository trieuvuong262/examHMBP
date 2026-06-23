from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from reports.models import DailyWorkReport, DailyWorkReportAttachment
from reports.report_profile import REPORT_PROFILE_OFFICE


@override_settings(NAS_MOUNT_ROOT='/tmp', NAS_DAILY_REPORT_REL_PATH='99_LUU_TRU/1.2026/BAO_CAO_NGAY')
class DailyOfficeAttachmentViewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='VP Attach',
            sort_order=1,
            report_profile=REPORT_PROFILE_OFFICE,
        )
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True}}},
        )
        self.user = User.objects.create_user(username='vp_user', password='x')
        Profile.objects.filter(user=self.user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='VP User',
            is_employed=True,
        )
        self.report = DailyWorkReport.objects.create(
            employee=self.user,
            report_date=timezone.localdate(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_DRAFT,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_today_vp_form_accepts_unified_attachment_field(self):
        pdf = SimpleUploadedFile('test.pdf', b'%PDF', content_type='application/pdf')
        png = SimpleUploadedFile('test.png', b'\x89PNG', content_type='image/png')
        url = reverse('reports:today_vp')
        resp = self.client.post(
            url,
            {
                'action': 'save',
                'report_date': self.report.report_date.isoformat(),
                'spreadsheet_data': '{"columns":["A"],"rows":[["x"]]}',
                'document_html': '',
                'attachments': [pdf, png],
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.report.attachments.count(), 2)
        self.assertEqual(
            self.report.attachments.filter(source_tab=DailyWorkReportAttachment.SOURCE_LINK).count(),
            2,
        )

    def test_submit_with_only_attachment_is_valid(self):
        pdf = SimpleUploadedFile('only.pdf', b'%PDF', content_type='application/pdf')
        url = reverse('reports:today_vp')
        resp = self.client.post(
            url,
            {
                'action': 'submit',
                'report_date': self.report.report_date.isoformat(),
                'spreadsheet_data': '{"columns":[""],"rows":[[""]]}',
                'document_html': '',
                'attachments': pdf,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, DailyWorkReport.STATUS_SUBMITTED)
        self.assertEqual(self.report.attachments.count(), 1)

    def test_today_vp_page_shows_unified_form_without_content_tabs(self):
        resp = self.client.get(reverse('reports:today_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="attachments"')
        self.assertContains(resp, 'Link &amp; đính kèm')
        self.assertNotContains(resp, 'id="vanban-tab"')
        self.assertNotContains(resp, 'id="bang-tab"')
        self.assertContains(resp, 'jp-office-panel-unified')

    def test_today_vp_period_tabs_have_visible_styles(self):
        resp = self.client.get(reverse('reports:today_vp'))
        self.assertContains(resp, 'jp-reports-period-tabs')
