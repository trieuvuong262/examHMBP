"""Test timeout rclone trong request phải nhỏ hơn `gunicorn --timeout`.

Trước đây các chỗ tải file NAS trong request dùng timeout=600 trong khi gunicorn
đặt --timeout 300 → worker bị kill trước, người dùng nhận 502/504.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from nas_storage.app_nas_storage import rclone_job_timeout, rclone_request_timeout

# Khớp `--timeout N` trong command gunicorn ở docker-compose.yml
COMPOSE_PATH = Path(__file__).resolve().parent.parent / 'docker-compose.yml'


def _gunicorn_timeout() -> int:
    text = COMPOSE_PATH.read_text(encoding='utf-8')
    match = re.search(r'gunicorn[^\n]*?--timeout\s+(\d+)', text)
    assert match, 'không tìm thấy gunicorn --timeout trong docker-compose.yml'
    return int(match.group(1))


class TimeoutBudgetTests(SimpleTestCase):
    def test_defaults(self):
        self.assertEqual(rclone_request_timeout(), 120)
        self.assertEqual(rclone_job_timeout(), 600)

    def test_request_timeout_below_gunicorn_timeout(self):
        """Bất biến quan trọng: timeout request < gunicorn --timeout."""
        self.assertLess(rclone_request_timeout(), _gunicorn_timeout())

    @override_settings(NAS_RCLONE_REQUEST_TIMEOUT=90, NAS_RCLONE_JOB_TIMEOUT=1200)
    def test_reads_settings(self):
        self.assertEqual(rclone_request_timeout(), 90)
        self.assertEqual(rclone_job_timeout(), 1200)

    @override_settings(NAS_RCLONE_REQUEST_TIMEOUT=9999)
    def test_request_timeout_capped_below_gunicorn(self):
        """Dù .env đặt sai cũng không được vượt ngưỡng gunicorn."""
        self.assertEqual(rclone_request_timeout(), 280)
        self.assertLess(rclone_request_timeout(), _gunicorn_timeout())

    @override_settings(NAS_RCLONE_REQUEST_TIMEOUT=1, NAS_RCLONE_JOB_TIMEOUT=1)
    def test_clamps_too_small(self):
        self.assertEqual(rclone_request_timeout(), 5)
        self.assertEqual(rclone_job_timeout(), 30)

    @override_settings(NAS_RCLONE_REQUEST_TIMEOUT='xx', NAS_RCLONE_JOB_TIMEOUT=None)
    def test_falls_back_on_bad_value(self):
        self.assertEqual(rclone_request_timeout(), 120)
        self.assertEqual(rclone_job_timeout(), 600)


class DownloadCallsUseRequestTimeoutTests(SimpleTestCase):
    """Cả 3 luồng tải file NAS trong request phải dùng ngân sách request."""

    def _assert_uses_request_timeout(self, module, func_name, target_patch):
        with tempfile.TemporaryDirectory() as tmp:
            cached = Path(tmp) / 'f.bin'

            def fake_run(cmd, **kwargs):
                cached.write_bytes(b'x')
                self.assertEqual(kwargs['timeout'], rclone_request_timeout())
                self.assertLess(kwargs['timeout'], _gunicorn_timeout())
                return type('P', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

            with patch.object(module, '_rclone_cache_path', return_value=cached), \
                    patch.object(module, target_patch, return_value='synology:x/f.bin'), \
                    patch.object(module.subprocess, 'run', side_effect=fake_run) as run:
                getattr(module, func_name)('f.bin')
            run.assert_called_once()

    def test_weekly_report_download(self):
        from reports import weekly_nas_storage as m

        self._assert_uses_request_timeout(m, '_rclone_download_to_cache', '_weekly_rclone_target')

    def test_daily_report_download(self):
        from reports import daily_nas_storage as m

        self._assert_uses_request_timeout(m, '_rclone_download_to_cache', '_daily_rclone_target')

    def test_announcement_download(self):
        from announcements import nas_storage as m

        self._assert_uses_request_timeout(m, '_rclone_download_to_cache', '_announcement_rclone_target')

    def test_persist_app_nas_file_uses_request_timeout(self):
        """Ghi file qua rclone khi allow_mount=True cũng phải dùng ngân sách request."""
        from nas_storage import app_nas_storage as m

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'a.txt'
            src.write_text('x', encoding='utf-8')

            seen = {}

            def fake_run(cmd, **kwargs):
                seen['timeout'] = kwargs['timeout']
                return type('P', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

            from nas_storage import nas_mount_health as mh

            with patch.object(mh, 'mount_io_safe', return_value=False), \
                    patch.object(m.subprocess, 'run', side_effect=fake_run):
                m.persist_app_nas_file(
                    tmp_path=src,
                    mount_dest=Path('/mnt/nas-portal/99_LUU_TRU/a.txt'),
                    folder_rel_base='99_LUU_TRU',
                    file_rel='a.txt',
                    allow_mount=True,
                )
            self.assertEqual(seen['timeout'], rclone_request_timeout())
            self.assertLess(seen['timeout'], _gunicorn_timeout())

    def test_persist_app_nas_file_no_mount_keeps_short_timeout(self):
        """allow_mount=False (báo cáo) vẫn giữ 90s để fail nhanh về lưu tạm."""
        from nas_storage import app_nas_storage as m

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'a.txt'
            src.write_text('x', encoding='utf-8')
            seen = {}

            def fake_run(cmd, **kwargs):
                seen['timeout'] = kwargs['timeout']
                seen['cmd'] = cmd
                return type('P', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

            with patch.object(m.subprocess, 'run', side_effect=fake_run):
                m.persist_app_nas_file(
                    tmp_path=src,
                    mount_dest=Path('/mnt/nas-portal/99_LUU_TRU/a.txt'),
                    folder_rel_base='99_LUU_TRU',
                    file_rel='a.txt',
                    allow_mount=False,
                )
            self.assertEqual(seen['timeout'], 90)
            self.assertIn('--contimeout', seen['cmd'])
