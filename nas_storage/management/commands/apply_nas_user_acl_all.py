"""Áp dụng mọi quyền truy cập riêng user lên NAS — chạy nền."""

import time
from pathlib import Path

from django.core.management.base import BaseCommand

from nas_storage.nas_acl_apply import NasAclApplyError, apply_all_user_folder_acls

_JOB = 'apply_nas_user_acl_all'


class Command(BaseCommand):
    help = 'Áp dụng ACL truy cập riêng (NasUserFolderAcl) lên Synology qua SSH.'

    def handle(self, *args, **options):
        lock = Path('/tmp') / f'nas_acl_job_{_JOB}.lock'
        lock.touch()
        started = time.time()
        try:
            result = apply_all_user_folder_acls()
        except NasAclApplyError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        finally:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                pass

        elapsed = int(time.time() - started)
        self.stdout.write(
            self.style.SUCCESS(
                f'Xong ({elapsed}s): ok={result["ok"]}, skipped={result["skipped"]}, '
                f'errors={len(result.get("errors") or [])}',
            ),
        )
        for err in (result.get('errors') or [])[:20]:
            self.stderr.write(self.style.WARNING(err))
