import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from announcements.models import Announcement
from announcements.nas_storage import (
    AnnouncementNasStorage,
    announcement_file_abs_path,
    announcement_nas_abs_root,
    ensure_announcement_nas_dir,
    is_legacy_announcement_path,
)


class AnnouncementNasStorageTests(TestCase):
    def setUp(self):
        self.nas_root = tempfile.mkdtemp()
        self.media_root = tempfile.mkdtemp()
        self.user = User.objects.create_user(username='ann_nas', password='x')
        self._override = override_settings(
            NAS_MOUNT_ROOT=self.nas_root,
            NAS_ANNOUNCEMENT_REL_PATH='99_LUU_TRU/1.2026/THONG_BAO',
            MEDIA_ROOT=self.media_root,
        )
        self._override.enable()

    def tearDown(self):
        self._override.disable()

    def test_upload_saves_under_nas_root(self):
        ensure_announcement_nas_dir()
        ann = Announcement.objects.create(
            title='Test NAS',
            content_type=Announcement.TYPE_PDF,
            created_by=self.user,
        )
        upload = SimpleUploadedFile('thong-bao.pdf', b'%PDF-test', content_type='application/pdf')
        ann.pdf_file.save('thong-bao.pdf', upload, save=True)

        path = announcement_file_abs_path(ann, 'pdf_file')
        self.assertIsNotNone(path)
        self.assertTrue(str(path).startswith(str(announcement_nas_abs_root())))
        self.assertTrue(path.is_file())
        self.assertFalse(is_legacy_announcement_path(ann.pdf_file.name))

    def test_original_file_upload(self):
        ensure_announcement_nas_dir()
        ann = Announcement.objects.create(
            title='Co dinh kem',
            content_type=Announcement.TYPE_TEXT,
            body='<p>Noi dung</p>',
            created_by=self.user,
        )
        upload = SimpleUploadedFile('van-ban-goc.docx', b'docx-bytes', content_type='application/vnd.openxmlformats')
        ann.original_file.save('van-ban-goc.docx', upload, save=True)

        path = announcement_file_abs_path(ann, 'original_file')
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())

    def test_legacy_path_detection(self):
        self.assertTrue(is_legacy_announcement_path('announcements/pdf/2026/a.pdf'))
        self.assertTrue(is_legacy_announcement_path('announcements/videos/clip.mp4'))
        self.assertFalse(is_legacy_announcement_path('2026/1/abc_file.pdf'))

    def test_legacy_file_readable_from_media(self):
        legacy_rel = 'announcements/pdf/2026/old.pdf'
        legacy_path = Path(self.media_root) / legacy_rel
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(b'legacy')

        storage = AnnouncementNasStorage()
        self.assertTrue(storage.exists(legacy_rel))
        with storage.open(legacy_rel) as fh:
            self.assertEqual(fh.read(), b'legacy')
        storage.delete(legacy_rel)
        self.assertFalse(legacy_path.is_file())

    def test_file_serve_view(self):
        ensure_announcement_nas_dir()
        ann = Announcement.objects.create(
            title='Serve test',
            content_type=Announcement.TYPE_TEXT,
            body='<p>Hi</p>',
            is_active=True,
            created_by=self.user,
        )
        upload = SimpleUploadedFile('goc.pdf', b'%PDF-serve', content_type='application/pdf')
        ann.original_file.save('goc.pdf', upload, save=True)

        client = Client(HTTP_HOST='testserver')
        client.force_login(self.user)
        url = ann.original_file_url
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'%PDF-serve', b''.join(response.streaming_content))
