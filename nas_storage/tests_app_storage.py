from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from nas_storage.app_nas_storage import persist_app_nas_file


@override_settings(NAS_MOUNT_ROOT='/mnt/nas-portal')
class PersistAppNasFileTests(SimpleTestCase):
    def test_mount_success_skips_rclone_and_dsm(self):
        tmp = Path(self._tmpdir()) / 'a.bin'
        tmp.write_bytes(b'ok')
        dest = Path(self._tmpdir()) / 'dest' / 'a.bin'
        with patch('nas_storage.app_nas_storage.shutil.copyfile') as copyfile:
            with patch('nas_storage.app_nas_storage.subprocess.run') as run:
                persist_app_nas_file(
                    tmp_path=tmp,
                    mount_dest=dest,
                    folder_rel_base='99_LUU_TRU/BAO_CAO',
                    file_rel='2026/x.bin',
                )
        copyfile.assert_called_once()
        run.assert_not_called()

    def test_mount_fail_then_rclone_ok(self):
        tmp = Path(self._tmpdir()) / 'b.bin'
        tmp.write_bytes(b'ok')
        dest = Path('/mnt/nas-portal/missing/b.bin')
        proc = MagicMock(returncode=0, stderr='', stdout='')
        with patch('nas_storage.app_nas_storage.Path.mkdir', side_effect=OSError('io')):
            with patch('nas_storage.app_nas_storage.subprocess.run', return_value=proc) as run:
                with patch('nas_storage.app_nas_storage.dsm_upload_nas_rel') as dsm:
                    persist_app_nas_file(
                        tmp_path=tmp,
                        mount_dest=dest,
                        folder_rel_base='99_LUU_TRU/BAO_CAO',
                        file_rel='2026/y.bin',
                    )
        run.assert_called_once()
        dsm.assert_not_called()

    def test_mount_and_rclone_fail_then_dsm(self):
        tmp = Path(self._tmpdir()) / 'c.bin'
        tmp.write_bytes(b'ok')
        dest = Path('/mnt/nas-portal/missing/c.bin')
        proc = MagicMock(returncode=1, stderr='smb fail', stdout='')
        with patch('nas_storage.app_nas_storage.Path.mkdir', side_effect=OSError('io')):
            with patch('nas_storage.app_nas_storage.subprocess.run', return_value=proc):
                with patch('nas_storage.app_nas_storage.dsm_upload_nas_rel') as dsm:
                    persist_app_nas_file(
                        tmp_path=tmp,
                        mount_dest=dest,
                        folder_rel_base='99_LUU_TRU/BAO_CAO',
                        file_rel='2026/z.bin',
                    )
        dsm.assert_called_once()

    def _tmpdir(self):
        import tempfile

        return tempfile.gettempdir()
