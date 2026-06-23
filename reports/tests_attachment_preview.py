from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport, DailyWorkReportAttachment
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.weekly_preview import file_attachment_preview


@override_settings(NAS_MOUNT_ROOT='/tmp', NAS_DAILY_REPORT_REL_PATH='99_LUU_TRU/1.2026/BAO_CAO_NGAY')
class AttachmentPreviewTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Preview Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        perms = {'reports': {'view': True, 'edit': True, 'create': True, 'update': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )
        self.member = User.objects.create_user(username='prev_mem', password='x')
        Profile.objects.filter(user=self.member).update(
            department=dept, role=ROLE_EMPLOYEE, full_name='Member', is_employed=True,
        )
        self.leader = User.objects.create_user(username='prev_lead', password='x')
        Profile.objects.filter(user=self.leader).update(
            department=dept, role=ROLE_TEAM_LEADER, full_name='Leader', is_employed=True,
        )
        self.leader.profile.subordinates.add(self.member)
        self.report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST='testserver')

    def _attach(self, name, content=b'data', **kwargs):
        return DailyWorkReportAttachment.objects.create(
            report=self.report,
            source_tab=DailyWorkReportAttachment.SOURCE_LINK,
            kind=DailyWorkReportAttachment.KIND_FILE,
            file=SimpleUploadedFile(name, content),
            original_name=name,
            **kwargs,
        )

    def test_file_attachment_preview_pdf(self):
        att = self._attach('bao-cao.pdf', b'%PDF-1.4')
        item = file_attachment_preview(att)
        self.assertEqual(item['type'], 'pdf')
        self.assertEqual(item['preview_url'], att.file_url)

    @patch('reports.weekly_preview.office_preview_available', return_value=True)
    def test_file_attachment_preview_xlsx(self, _mock_lo):
        att = self._attach('data.xlsx', b'PK')
        item = file_attachment_preview(att)
        self.assertEqual(item['type'], 'office')
        self.assertTrue(item['office_preview_ready'])
        self.assertIn('/preview/', item['preview_url'])

    def test_detail_shows_pdf_embed(self):
        att = self._attach('bao-cao.pdf', b'%PDF-1.4 test')
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:detail_vp', args=[self.report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'jp-weekly-embed-wrap is-pdf')
        self.assertContains(resp, att.file_url)

    @patch('tools.services.office_preview_available', return_value=True)
    @patch('nas_storage.file_preview.inline_office_pdf_response')
    def test_office_preview_endpoint(self, mock_preview, _mock_lo):
        mock_preview.return_value = HttpResponse(b'%PDF-mock', content_type='application/pdf')
        att = self._attach('report.docx', b'docx')
        self.client.force_login(self.leader)
        preview_url = reverse('reports:daily_attachment_preview', args=[att.pk])
        resp = self.client.get(preview_url)
        self.assertEqual(resp.status_code, 200)
        mock_preview.assert_called_once()

    @patch('reports.weekly_preview.office_preview_available', return_value=True)
    def test_detail_shows_office_embed(self, _mock_lo):
        att = self._attach('report.xlsx', b'PK')
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:detail_vp', args=[self.report.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('reports:daily_attachment_preview', args=[att.pk]))
