"""Test tích hợp: view gửi báo cáo phải từ chối file độc hại, không ghi lên NAS."""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE

PDF = b'%PDF-1.7\n' + b'0' * 32
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32
EXE = b'MZ\x90\x00' + b'0' * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@override_settings(NAS_MOUNT_ROOT='/tmp', NAS_DAILY_REPORT_REL_PATH='99_LUU_TRU/1.2026/BAO_CAO_NGAY')
class DailyReportUploadGuardViewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name='VP Guard',
            sort_order=1,
            report_profile=REPORT_PROFILE_OFFICE,
        )
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True}}},
        )
        self.user = User.objects.create_user(username='vp_guard', password='x')
        Profile.objects.filter(user=self.user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            full_name='VP Guard',
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

    def _post(self, **files):
        return self.client.post(reverse('reports:today_vp'), {
            'action': 'save',
            'report_date': self.report.report_date.isoformat(),
            'spreadsheet_data': '{"columns":["A"],"rows":[["x"]]}',
            'document_html': '',
            **files,
        })

    def _messages(self, resp):
        from django.contrib.messages import get_messages

        return ' '.join(str(m) for m in get_messages(resp.wsgi_request))

    # Phần "không chặn oan" được phủ bởi
    # nas_storage.tests_upload_guard.AcceptsRealWorldFilesTests — kiểm ở tầng
    # validator nên không phụ thuộc NAS/rclone. Ở đây chỉ kiểm nhánh TỪ CHỐI,
    # vì nhánh đó chạy trước mọi I/O nên chạy được ở mọi môi trường.

    def test_rejects_executable(self):
        resp = self._post(link_files=SimpleUploadedFile('virus.exe', EXE))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.report.attachments.count(), 0)
        self.assertIn('không được phép', self._messages(resp))

    def test_rejects_exe_disguised_as_pdf(self):
        """Đổi tên .exe thành .pdf — chặn bằng magic bytes."""
        resp = self._post(link_files=SimpleUploadedFile('bao-cao.pdf', EXE))
        self.assertEqual(self.report.attachments.count(), 0)
        self.assertIn('thực thi Windows', self._messages(resp))

    def test_rejects_double_extension(self):
        resp = self._post(link_files=SimpleUploadedFile('bao-cao.pdf.exe', PDF))
        self.assertEqual(self.report.attachments.count(), 0)

    def test_rejects_svg(self):
        resp = self._post(link_files=SimpleUploadedFile('logo.svg', SVG))
        self.assertEqual(self.report.attachments.count(), 0)

    def test_image_field_rejects_pdf(self):
        """Ô ảnh chỉ nhận ảnh."""
        resp = self._post(link_images=SimpleUploadedFile('bao-cao.pdf', PDF))
        self.assertEqual(self.report.attachments.count(), 0)

    def test_rejection_does_not_break_request(self):
        """Đính kèm sai chỉ báo lỗi, không làm vỡ request (302 như bình thường)."""
        resp = self._post(link_files=SimpleUploadedFile('virus.exe', EXE))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.report.attachments.count(), 0)
        self.assertTrue(self._messages(resp))

    def test_no_file_written_for_rejected_upload(self):
        """Không được để lại file rác trên NAS/đĩa khi đã từ chối."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(NAS_MOUNT_ROOT=tmp):
                self._post(link_files=SimpleUploadedFile('virus.exe', EXE))
            leftovers = [
                os.path.join(root, f)
                for root, _dirs, fs in os.walk(tmp) for f in fs
            ]
        self.assertEqual(leftovers, [])


@override_settings(NAS_MOUNT_ROOT='/tmp')
class AttachmentServingHeaderTests(TestCase):
    """SVG không được render inline; response tải file phải có CSP."""

    def test_svg_removed_from_inline_types(self):
        import inspect

        from reports import views

        for fn_name in ('daily_attachment_download', 'weekly_attachment_download'):
            fn = getattr(views, fn_name, None)
            if fn is None:
                continue
            src = inspect.getsource(fn)
            with self.subTest(view=fn_name):
                self.assertNotIn('image/svg+xml', src)
                self.assertIn('Content-Security-Policy', src)
