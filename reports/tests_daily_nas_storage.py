import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from reports.models import DailyWorkReport, DailyWorkReportAttachment
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.daily_nas_storage import (
    DailyReportNasStorage,
    daily_attachment_abs_path,
    daily_report_nas_abs_root,
    ensure_daily_report_nas_dir,
)
from reports.daily_uploads import save_daily_uploads


class DailyNasStorageTests(TestCase):
    def setUp(self):
        self.nas_root = tempfile.mkdtemp()
        self.media_root = tempfile.mkdtemp()
        self.user = User.objects.create_user(username='daily_nas', password='x')
        self.report = DailyWorkReport.objects.create(
            employee=self.user,
            report_date=date(2026, 5, 28),
            report_profile=REPORT_PROFILE_OFFICE,
        )
        self._override = override_settings(
            NAS_MOUNT_ROOT=self.nas_root,
            NAS_DAILY_REPORT_REL_PATH='99_LUU_TRU/1.2026/BAO_CAO_NGAY',
            MEDIA_ROOT=self.media_root,
        )
        self._override.enable()

    def tearDown(self):
        self._override.disable()

    def test_upload_saves_under_nas_root(self):
        ensure_daily_report_nas_dir()
        upload = SimpleUploadedFile('bao-cao.pdf', b'%PDF-test', content_type='application/pdf')
        created = save_daily_uploads(self.report, bang_files=[upload])
        self.assertEqual(len(created), 1)
        att = created[0]
        self.assertEqual(att.source_tab, DailyWorkReportAttachment.SOURCE_BANG)
        path = daily_attachment_abs_path(att)
        self.assertIsNotNone(path)
        self.assertTrue(str(path).startswith(str(daily_report_nas_abs_root())))
        self.assertTrue(path.is_file())

    def test_storage_path_includes_tab_folder(self):
        ensure_daily_report_nas_dir()
        upload = SimpleUploadedFile('photo.png', b'\x89PNG', content_type='image/png')
        created = save_daily_uploads(self.report, vanban_images=[upload])
        rel = created[0].file.name
        self.assertIn('/vanban/', rel)
        storage = DailyReportNasStorage()
        self.assertTrue(Path(storage.path(rel)).is_file())
