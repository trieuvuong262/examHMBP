"""Test lop hang doi job nen — phai an toan khi khong co Redis."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from PortalJustPlay import background

_calls = []


def _record(*args, **kwargs):
    """Ham cap module — RQ chi serialize duoc ham import duoc."""
    _calls.append((args, kwargs))
    return len(_calls)


def _boom():
    raise RuntimeError('job loi co y')


class BackgroundEagerTests(SimpleTestCase):
    def setUp(self):
        _calls.clear()

    @override_settings(BACKGROUND_TASKS_EAGER=True, RQ_QUEUES={})
    def test_eager_runs_immediately(self):
        result = background.enqueue(_record, 1, x=2)
        self.assertIsNone(result, 'Che do eager khong tra job')
        self.assertEqual(_calls, [((1,), {'x': 2})])

    @override_settings(BACKGROUND_TASKS_EAGER=True, RQ_QUEUES={})
    def test_eager_propagates_error(self):
        with self.assertRaises(RuntimeError):
            background.enqueue(_boom)

    @override_settings(BACKGROUND_TASKS_EAGER=True, RQ_QUEUES={})
    def test_queue_unavailable_when_eager(self):
        self.assertFalse(background.queue_available())


class BackgroundThreadFallbackTests(SimpleTestCase):
    """Khong co Redis -> chay bang thread, khong duoc nem loi ra request."""

    def setUp(self):
        _calls.clear()

    @override_settings(BACKGROUND_TASKS_EAGER=False, RQ_QUEUES={})
    def test_falls_back_to_thread(self):
        thread = background.enqueue(_record, 'a')
        self.assertIsNotNone(thread)
        thread.join(timeout=5)
        self.assertEqual(_calls, [(('a',), {})])

    @override_settings(BACKGROUND_TASKS_EAGER=False, RQ_QUEUES={})
    def test_thread_swallows_error(self):
        thread = background.enqueue(_boom)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), 'Loi trong job khong duoc lam gay request')

    @override_settings(
        BACKGROUND_TASKS_EAGER=False,
        RQ_QUEUES={'default': {'URL': 'redis://khong-ton-tai:6379/0'}},
    )
    def test_redis_down_falls_back_to_thread(self):
        thread = background.enqueue(_record, 'b')
        self.assertIsNotNone(thread, 'Redis chet van phai chay duoc bang thread')
        thread.join(timeout=5)
        self.assertEqual(_calls, [(('b',), {})])


class BackgroundQueueTests(SimpleTestCase):
    """Co Redis -> phai day vao dung hang doi."""

    def setUp(self):
        _calls.clear()

    @override_settings(
        BACKGROUND_TASKS_EAGER=False,
        RQ_QUEUES={'default': {'URL': 'redis://x:6379/0'},
                   'nas': {'URL': 'redis://x:6379/0'}},
    )
    def test_enqueues_to_named_queue(self):
        fake_queue = type('Q', (), {'enqueue': lambda self, *a, **k: 'JOB'})()
        with patch.object(background, 'queue_available', return_value=True), \
                patch('django_rq.get_queue', return_value=fake_queue) as get_queue:
            job = background.enqueue(_record, 1, queue=background.QUEUE_NAS)
        self.assertEqual(job, 'JOB')
        get_queue.assert_called_once_with('nas')
        self.assertEqual(_calls, [], 'Day vao hang doi thi khong chay ngay')

    @override_settings(RQ_QUEUES={})
    def test_stats_empty_without_queues(self):
        self.assertEqual(background.queue_stats(), [])


class NasInstallerCacheTests(SimpleTestCase):
    """Installer NAS phai stream, khong nap het vao RAM."""

    def test_stream_file_uses_fileresponse(self):
        import tempfile
        from pathlib import Path

        from django.http import FileResponse

        from nas_storage.views_nas_download import _stream_file

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'test.exe'
            p.write_bytes(b'x' * 2048)
            resp = _stream_file(p, 'test.exe')
            try:
                self.assertIsInstance(resp, FileResponse)
                self.assertEqual(resp['Content-Length'], '2048')
                self.assertIn('attachment', resp['Content-Disposition'])
                self.assertTrue(resp.streaming, 'Phai la response dang stream')
            finally:
                resp.close()

    def test_cache_installer_copies_file(self):
        import tempfile
        from pathlib import Path

        from nas_storage import views_nas_download as mod

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'RaiDrive_x64.exe'
            src.write_bytes(b'INSTALLER')
            cache_dir = Path(tmp) / 'cache'
            with patch.object(mod, '_installer_cache_dir', return_value=cache_dir):
                out = mod.cache_installer_from_nas(str(src), 'RaiDrive_x64.exe')
                self.assertIsNotNone(out)
                self.assertEqual(Path(out).read_bytes(), b'INSTALLER')
                self.assertEqual(mod._cached_raidrive_installer(), Path(out))

    def test_cache_missing_source_returns_none(self):
        from nas_storage.views_nas_download import cache_installer_from_nas

        self.assertIsNone(cache_installer_from_nas('/khong/co/file.exe', 'a.exe'))
