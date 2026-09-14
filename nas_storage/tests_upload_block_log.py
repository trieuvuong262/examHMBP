"""Log chi tiet khi chan upload — user / file / code."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

from audit.models import UserActivityLog
from nas_storage.upload_guard import UploadRejected, upload_audit, validate_upload, validate_uploads

User = get_user_model()

JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


class UploadBlockLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("uploader", password="x")
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.post("/reports/sx/today/")
        request.user = self.user
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        request.META["HTTP_USER_AGENT"] = "test-agent"
        return request

    def test_dangerous_ext_logs_user_and_writes_activity(self):
        request = self._request()
        bad = SimpleUploadedFile(
            "virus.exe", b"MZ\x90\x00", content_type="application/octet-stream"
        )
        with upload_audit(request), self.assertRaises(UploadRejected):
            validate_upload(bad, scan=False)

        log = UserActivityLog.objects.filter(object_type="upload_rejected").latest("pk")
        self.assertEqual(log.username, "uploader")
        self.assertIn("virus.exe", log.summary)
        self.assertEqual(log.extra["upload_block"]["code"], "dangerous_ext")
        self.assertEqual(log.extra["upload_block"]["filename"], "virus.exe")

    @override_settings(AV_SCAN_FORCE_OFF=False)
    def test_malware_block_includes_signature(self):
        request = self._request()
        clean_looking = SimpleUploadedFile("anh.jpg", JPEG, content_type="image/jpeg")

        fake_result = MagicMock(
            is_infected=True,
            is_clean=False,
            signature="Eicar-Test-Signature",
            detail="stream: Eicar-Test-Signature FOUND",
        )
        with (
            upload_audit(request),
            patch("nas_storage.av_scan.av_enabled", return_value=True),
            patch("nas_storage.av_scan.scan_upload", return_value=fake_result),
            self.assertRaises(UploadRejected),
        ):
            validate_upload(clean_looking, scan=True)

        log = UserActivityLog.objects.filter(object_type="upload_rejected").latest("pk")
        self.assertEqual(log.extra["upload_block"]["code"], "malware")
        self.assertEqual(log.extra["upload_block"]["signature"], "Eicar-Test-Signature")
        self.assertIn("uploader", log.summary)

    def test_validate_uploads_request_kwarg_binds_audit(self):
        request = self._request()
        bad = SimpleUploadedFile("bad.js", b"alert(1)", content_type="text/javascript")
        with self.assertRaises(UploadRejected):
            validate_uploads([bad], request=request)
        self.assertTrue(
            UserActivityLog.objects.filter(
                object_type="upload_rejected",
                username="uploader",
            ).exists()
        )

    def test_without_request_still_raises_and_logs_warning(self):
        bad = SimpleUploadedFile("a.exe", b"MZ", content_type="application/octet-stream")
        with self.assertLogs("nas_storage.upload_guard", level="WARNING") as cm:
            with self.assertRaises(UploadRejected):
                validate_upload(bad, scan=False)
        self.assertTrue(any("UPLOAD_BLOCKED" in line and "a.exe" in line for line in cm.output))
        self.assertFalse(
            UserActivityLog.objects.filter(object_type="upload_rejected").exists()
        )

class PartitionUploadsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("partuser", password="x")
        self.factory = RequestFactory()

    def test_keeps_good_files_and_lists_rejects(self):
        request = self.factory.post("/reports/")
        request.user = self.user
        good = SimpleUploadedFile("anh.jpg", JPEG, content_type="image/jpeg")
        bad = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        from nas_storage.upload_guard import partition_uploads

        accepted, rejected = partition_uploads([good, bad], request=request)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(getattr(accepted[0], "name", ""), "anh.jpg")
        self.assertEqual(len(rejected), 1)
        self.assertIn("virus.exe", rejected[0])

    def test_accepts_psd_magic(self):
        from nas_storage.upload_guard import validate_upload

        psd = SimpleUploadedFile(
            "mau.psd",
            b"8BPS" + b"\x00" * 20,
            content_type="image/vnd.adobe.photoshop",
        )
        self.assertEqual(validate_upload(psd, scan=False), "mau.psd")
