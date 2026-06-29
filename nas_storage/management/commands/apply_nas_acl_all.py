"""Áp dụng mọi quyền thư mục NAS lên Synology — dùng từ view nền hoặc cron."""

import time
from pathlib import Path

from django.core.management.base import BaseCommand

from nas_storage.nas_acl_apply import NasAclApplyError, apply_all_folder_permissions

_JOB = 'apply_nas_acl_all'


class Command(BaseCommand):
    help = 'Áp dụng ACL mọi thư mục NAS lên Synology qua SSH (batch).'

    def handle(self, *args, **options):
        lock = Path('/tmp') / f'nas_acl_job_{_JOB}.lock'
        lock.touch()
        started = time.time()
        try:
            result = apply_all_folder_permissions()
        except NasAclApplyError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Lỗi: {exc}'))
            raise
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
