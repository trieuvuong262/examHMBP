import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from reports.models import WeeklyWorkReport, WeeklyWorkReportAttachment
from reports.weekly_nas_storage import (
    LEGACY_WEEKLY_PREFIX,
    WeeklyReportNasStorage,
    ensure_weekly_report_nas_dir,
    is_legacy_weekly_path,
    weekly_attachment_abs_path,
    weekly_report_nas_abs_root,
)
from reports.weekly_uploads import save_weekly_uploads


class WeeklyNasStorageTests(TestCase):
    def setUp(self):
        self.nas_root = tempfile.mkdtemp()
        self.media_root = tempfile.mkdtemp()
        self.user = User.objects.create_user(username='weekly_nas', password='x')
        self.report = WeeklyWorkReport.objects.create(
            employee=self.user,
            week_start=date(2026, 5, 25),
            links='',
        )
        self._override = override_settings(
            NAS_MOUNT_ROOT=self.nas_root,
            NAS_WEEKLY_REPORT_REL_PATH='99_LUU_TRU/1.2026/BAO_CAO_TUAN',
            MEDIA_ROOT=self.media_root,
        )
        self._override.enable()

    def tearDown(self):
        self._override.disable()

    def test_upload_saves_under_nas_root(self):
        ensure_weekly_report_nas_dir()
        upload = SimpleUploadedFile('bao-cao.pdf', b'%PDF-test', content_type='application/pdf')
        created = save_weekly_uploads(self.report, file_list=[upload])
        self.assertEqual(len(created), 1)
        att = created[0]
        path = weekly_attachment_abs_path(att)
        self.assertIsNotNone(path)
        self.assertTrue(str(path).startswith(str(weekly_report_nas_abs_root())))
        self.assertTrue(path.is_file())
        self.assertFalse(att.file.name.startswith(LEGACY_WEEKLY_PREFIX))

    def test_legacy_path_detection(self):
        self.assertTrue(is_legacy_weekly_path('reports/weekly/2026/05/a.pdf'))
        self.assertFalse(is_legacy_weekly_path('2026/W21/user/a.pdf'))

    def test_legacy_file_readable_from_media(self):
        legacy_rel = 'reports/weekly/2026/05/old.pdf'
        legacy_path = Path(self.media_root) / legacy_rel
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(b'legacy')

        storage = WeeklyReportNasStorage()
        self.assertTrue(storage.exists(legacy_rel))
        with storage.open(legacy_rel) as fh:
            self.assertEqual(fh.read(), b'legacy')
        storage.delete(legacy_rel)
        self.assertFalse(legacy_path.is_file())
