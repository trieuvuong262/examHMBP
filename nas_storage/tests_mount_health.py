"""Test guard chống treo mount FUSE (D-state) khi NAS mất kết nối."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from nas_storage import nas_mount_health as mh

# Mẫu thật từ /proc/self/mountinfo trên VPS: mount rclone kiểu fuse.rclone
MOUNTINFO_WITH_FUSE = """\
25 30 0:24 / /proc rw,nosuid,nodev,noexec,relatime shared:12 - proc proc rw
36 25 0:31 / / rw,relatime shared:1 - ext4 /dev/sda1 rw
812 36 0:77 / /mnt/nas-portal rw,nosuid,nodev,relatime shared:400 - fuse.rclone rclone rw,user_id=0,group_id=0
813 36 0:78 / /mnt/nas-kd-mkt rw,nosuid,nodev,relatime shared:401 - fuse.rclone rclone rw,user_id=0,group_id=0
"""

MOUNTINFO_NO_FUSE = """\
25 30 0:24 / /proc rw,nosuid,nodev,noexec,relatime shared:12 - proc proc rw
36 25 0:31 / / rw,relatime shared:1 - ext4 /dev/sda1 rw
"""

# Mount point có khoảng trắng — mountinfo escape thành \\040
MOUNTINFO_ESCAPED = """\
812 36 0:77 / /mnt/nas\\040portal rw,relatime shared:400 - fuse.rclone rclone rw
"""


class FuseDetectionTests(SimpleTestCase):
    def setUp(self):
        mh.reset_fuse_cache()
        self.addCleanup(mh.reset_fuse_cache)

    def test_parses_fuse_mount_points(self):
        with patch('builtins.open', _fake_open(MOUNTINFO_WITH_FUSE)):
            points = mh.fuse_mount_points(use_cache=False)
        self.assertEqual(points, ('/mnt/nas-portal', '/mnt/nas-kd-mkt'))

    def test_ignores_non_fuse_filesystems(self):
        with patch('builtins.open', _fake_open(MOUNTINFO_NO_FUSE)):
            points = mh.fuse_mount_points(use_cache=False)
        self.assertEqual(points, ())

    def test_unescapes_mount_point_with_space(self):
        with patch('builtins.open', _fake_open(MOUNTINFO_ESCAPED)):
            points = mh.fuse_mount_points(use_cache=False)
        self.assertEqual(points, ('/mnt/nas portal',))

    def test_missing_procfs_returns_empty(self):
        with patch('builtins.open', side_effect=OSError('no procfs')):
            points = mh.fuse_mount_points(use_cache=False)
        self.assertEqual(points, ())

    def test_path_on_fuse_mount_matches_mount_and_children(self):
        with patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)):
            self.assertTrue(mh.path_on_fuse_mount('/mnt/nas-portal'))
            self.assertTrue(mh.path_on_fuse_mount('/mnt/nas-portal/IT/file.pdf'))
            self.assertTrue(mh.path_on_fuse_mount(Path('/mnt/nas-portal/IT')))
            # Tiền tố giống nhưng khác thư mục — không được coi là trên mount
            self.assertFalse(mh.path_on_fuse_mount('/mnt/nas-portal-backup/x'))
            self.assertFalse(mh.path_on_fuse_mount('/tmp/whatever'))


class MountIoSafeTests(SimpleTestCase):
    def setUp(self):
        mh.reset_fuse_cache()
        cache.delete(mh._REMOTE_CACHE_KEY)
        self.addCleanup(mh.reset_fuse_cache)
        self.addCleanup(cache.delete, mh._REMOTE_CACHE_KEY)

    def test_non_fuse_path_never_probes(self):
        """Thư mục thường (dev/test): cho phép ngay, không gọi rclone."""
        with patch.object(mh, 'fuse_mount_points', return_value=()), \
                patch.object(mh, '_probe_remote_reachable') as probe:
            self.assertTrue(mh.mount_io_safe('/tmp/nas-test'))
        probe.assert_not_called()

    def test_fuse_path_blocked_when_remote_down(self):
        with patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)), \
                patch.object(mh, '_probe_remote_reachable', return_value=False):
            self.assertFalse(mh.mount_io_safe('/mnt/nas-portal/IT/a.pdf'))

    def test_fuse_path_allowed_when_remote_up(self):
        with patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)), \
                patch.object(mh, '_probe_remote_reachable', return_value=True):
            self.assertTrue(mh.mount_io_safe('/mnt/nas-portal/IT/a.pdf'))

    def test_probe_result_is_cached(self):
        with patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)), \
                patch.object(mh, '_probe_remote_reachable', return_value=True) as probe:
            mh.mount_io_safe('/mnt/nas-portal')
            mh.mount_io_safe('/mnt/nas-portal')
            mh.mount_io_safe('/mnt/nas-portal')
        self.assertEqual(probe.call_count, 1)

    def test_mark_remote_unavailable_blocks_immediately(self):
        with patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)), \
                patch.object(mh, '_probe_remote_reachable', return_value=True):
            self.assertTrue(mh.mount_io_safe('/mnt/nas-portal'))
            mh.mark_remote_unavailable()
            self.assertFalse(mh.mount_io_safe('/mnt/nas-portal'))

    def test_probe_exception_treated_as_unreachable(self):
        with patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)), \
                patch.object(mh, '_probe_remote_reachable', side_effect=RuntimeError('boom')):
            self.assertFalse(mh.mount_io_safe('/mnt/nas-portal'))

    def test_guard_mount_io_raises_when_unsafe(self):
        with patch.object(mh, 'mount_io_safe', return_value=False):
            with self.assertRaises(OSError):
                mh.guard_mount_io('/mnt/nas-portal', what='thông báo')

    def test_guard_mount_io_passes_when_safe(self):
        with patch.object(mh, 'mount_io_safe', return_value=True):
            mh.guard_mount_io('/mnt/nas-portal')  # không raise


class NasPathsGuardTests(SimpleTestCase):
    """Guard phải chặn I/O ở tầng nas_paths khi NAS treo."""

    def setUp(self):
        mh.reset_fuse_cache()
        cache.delete(mh._REMOTE_CACHE_KEY)
        self.addCleanup(mh.reset_fuse_cache)
        self.addCleanup(cache.delete, mh._REMOTE_CACHE_KEY)

    def test_nas_is_available_uses_probe_on_fuse_not_stat(self):
        from nas_storage import nas_paths

        with override_settings(NAS_MOUNT_ROOT='/mnt/nas-portal'), \
                patch.object(mh, 'fuse_mount_points', return_value=('/mnt/nas-portal',)), \
                patch.object(mh, '_probe_remote_reachable', return_value=False), \
                patch('pathlib.Path.is_dir', side_effect=AssertionError('không được stat mount')):
            self.assertFalse(nas_paths.nas_is_available())

    def test_nas_is_available_stats_plain_directory(self):
        from nas_storage import nas_paths

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(NAS_MOUNT_ROOT=tmp), \
                    patch.object(mh, 'fuse_mount_points', return_value=()), \
                    patch.object(mh, '_probe_remote_reachable') as probe:
                self.assertTrue(nas_paths.nas_is_available())
            probe.assert_not_called()

    def test_list_directory_local_refuses_when_mount_unsafe(self):
        from nas_storage import nas_paths

        with patch.object(mh, 'mount_io_safe', return_value=False), \
                patch('pathlib.Path.is_dir', side_effect=AssertionError('không được stat mount')):
            with self.assertRaises(nas_paths.NasPathError):
                nas_paths._list_directory_local(Path('/mnt/nas-portal/IT'))

    def test_list_directory_with_source_falls_back_to_rclone(self):
        """Mount treo → không chạm mount, dùng rclone."""
        from nas_storage import nas_paths

        listing = {'folders': [{'name': 'x', 'modified': 0}], 'files': []}
        with patch.object(mh, 'mount_io_safe', return_value=False), \
                patch.object(nas_paths, 'rclone_listing_available', return_value=True), \
                patch.object(nas_paths, 'list_directory_via_rclone', return_value=listing) as rc, \
                patch('pathlib.Path.is_dir', side_effect=AssertionError('không được stat mount')):
            result, source, _stale = nas_paths.list_directory_with_source(
                Path('/mnt/nas-portal/IT'), rel_path='IT',
            )
        self.assertEqual(source, 'rclone')
        self.assertEqual(result['folders'][0]['name'], 'x')
        rc.assert_called_once()

    def test_list_directory_with_source_raises_when_no_rclone(self):
        from nas_storage import nas_paths

        with patch.object(mh, 'mount_io_safe', return_value=False), \
                patch.object(nas_paths, 'rclone_listing_available', return_value=False), \
                patch('pathlib.Path.is_dir', side_effect=AssertionError('không được stat mount')):
            with self.assertRaises(nas_paths.NasPathError):
                nas_paths.list_directory_with_source(Path('/mnt/nas-portal/IT'), rel_path='IT')


class AppNasStorageGuardTests(SimpleTestCase):
    def setUp(self):
        mh.reset_fuse_cache()
        cache.delete(mh._REMOTE_CACHE_KEY)
        self.addCleanup(mh.reset_fuse_cache)
        self.addCleanup(cache.delete, mh._REMOTE_CACHE_KEY)

    def test_persist_skips_mount_copy_when_unsafe(self):
        """NAS treo → không shutil.copyfile lên mount, đi thẳng rclone."""
        from nas_storage import app_nas_storage

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'a.txt'
            src.write_text('x', encoding='utf-8')

            with patch.object(mh, 'mount_io_safe', return_value=False), \
                    patch.object(app_nas_storage.shutil, 'copyfile',
                                 side_effect=AssertionError('không được chạm mount')), \
                    patch.object(app_nas_storage.subprocess, 'run') as run:
                run.return_value = type('P', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
                app_nas_storage.persist_app_nas_file(
                    tmp_path=src,
                    mount_dest=Path('/mnt/nas-portal/99_LUU_TRU/a.txt'),
                    folder_rel_base='99_LUU_TRU',
                    file_rel='a.txt',
                    allow_mount=True,
                )
            run.assert_called_once()
            self.assertIn('copyto', run.call_args[0][0])


def _fake_open(content: str):
    """patch builtins.open trả về nội dung mountinfo giả."""
    import io

    def _open(path, *args, **kwargs):
        if str(path) == mh.MOUNTINFO_PATH:
            return io.StringIO(content)
        raise AssertionError(f'unexpected open: {path}')

    return _open
