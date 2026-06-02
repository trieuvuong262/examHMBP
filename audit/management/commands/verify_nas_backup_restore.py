"""Kiểm tra file backup NAS có khôi phục được (DB → DB tạm, tar → giải nén)."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from audit.portal_backup import (
    PortalBackupError,
    _rclone_env,
    rclone_listing_available,
    sanitize_pg_dump_sql,
)


class Command(BaseCommand):
    help = 'Tải backup từ NAS và thử khôi phục (database tạm, không ghi đè DB chính).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--remote',
            required=True,
            help='Thư mục backup trên NAS, vd synology:backup/2026-06-02/20260602-165908-man',
        )
        parser.add_argument(
            '--skip-db',
            action='store_true',
            help='Chỉ kiểm tra file tar/sql, không tạo DB tạm',
        )

    def handle(self, *args, **options):
        remote = (options['remote'] or '').strip().rstrip('/')
        if not remote:
            raise CommandError('Thiếu --remote')
        if not rclone_listing_available():
            raise CommandError('rclone chưa sẵn sàng trên server.')

        work = Path(tempfile.mkdtemp(prefix='portal-restore-verify-'))
        try:
            self.stdout.write(f'Tải backup: {remote}')
            proc = subprocess.run(
                ['rclone', 'copy', remote, str(work)],
                capture_output=True,
                text=True,
                timeout=7200,
                check=False,
                env=_rclone_env(),
            )
            if proc.returncode != 0:
                raise CommandError((proc.stderr or proc.stdout or 'rclone copy thất bại').strip())

            sql_gz = work / 'database.sql.gz'
            if not sql_gz.is_file():
                raise CommandError('Thiếu database.sql.gz')

            with gzip.open(sql_gz, 'rb') as gz:
                head = gz.read(4096).decode('utf-8', errors='replace')
            if 'PostgreSQL database dump' not in head and 'CREATE TABLE' not in head:
                raise CommandError('database.sql.gz không phải dump PostgreSQL hợp lệ.')
            self.stdout.write(self.style.SUCCESS('OK: database.sql.gz (PostgreSQL dump)'))

            manifest_path = work / 'manifest.json'
            if manifest_path.is_file():
                meta = json.loads(manifest_path.read_text(encoding='utf-8'))
                self.stdout.write(f'  manifest: {len(meta.get("artifacts", []))} artifact(s)')

            source_tars = sorted(work.glob('source-*.tar.gz'))
            if not source_tars:
                raise CommandError('Thiếu source-*.tar.gz')
            with tarfile.open(source_tars[0], 'r:gz') as tar:
                names = tar.getnames()
            if not any(n.endswith('manage.py') for n in names):
                raise CommandError('source tar không chứa manage.py')
            self.stdout.write(self.style.SUCCESS(f'OK: {source_tars[0].name} ({len(names)} paths, có manage.py)'))

            media_tar = work / 'media.tar.gz'
            if media_tar.is_file():
                with tarfile.open(media_tar, 'r:gz') as tar:
                    media_count = len(tar.getmembers())
                self.stdout.write(self.style.SUCCESS(f'OK: media.tar.gz ({media_count} entries)'))

            if options['skip_db']:
                self.stdout.write(self.style.WARNING('Bỏ qua restore DB (--skip-db).'))
                return

            test_db = 'portal_restore_verify'
            self._restore_db_to_temp(test_db, sql_gz)
            self.stdout.write(self.style.SUCCESS(f'OK: restore DB vào "{test_db}" thành công'))
            self._drop_temp_db(test_db)
            self.stdout.write(self.style.SUCCESS('Đã xóa DB tạm — production không bị đổi.'))
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Kết luận: CÓ THỂ khôi phục từ backup này.'))

        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _psql_base(self) -> list[str]:
        db = settings.DATABASES['default']
        env = {'PGPASSWORD': str(db.get('PASSWORD') or '')}
        return [
            'psql',
            '-h', str(db.get('HOST') or 'localhost'),
            '-p', str(db.get('PORT') or '5432'),
            '-U', str(db.get('USER') or 'postgres'),
        ], env

    def _run_psql(self, args: list[str], *, input_sql: bytes | None = None) -> None:
        cmd, env = self._psql_base()
        proc = subprocess.run(
            cmd + args,
            input=input_sql,
            capture_output=True,
            check=False,
            env={**__import__('os').environ, **env},
            timeout=3600,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace')[:3000]
            raise CommandError(err or 'psql lỗi')

    def _restore_db_to_temp(self, test_db: str, sql_gz: Path) -> None:
        self._drop_temp_db(test_db, ignore_missing=True)
        self._run_psql(['-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', f'CREATE DATABASE "{test_db}";'])
        with gzip.open(sql_gz, 'rb') as gz:
            sql_data = sanitize_pg_dump_sql(gz.read())
        cmd, env = self._psql_base()
        proc = subprocess.run(
            cmd + ['-d', test_db, '-v', 'ON_ERROR_STOP=1'],
            input=sql_data,
            capture_output=True,
            check=False,
            env={**__import__('os').environ, **env},
            timeout=3600,
        )
        if proc.returncode != 0:
            self._drop_temp_db(test_db, ignore_missing=True)
            err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace')[:3000]
            raise CommandError(f'Restore SQL thất bại: {err}')

        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')  # noqa: ensure django db module loaded

        cmd, env = self._psql_base()
        proc = subprocess.run(
            cmd + ['-d', test_db, '-t', '-c',
                   "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"],
            capture_output=True,
            text=True,
            check=False,
            env={**__import__('os').environ, **env},
        )
        if proc.returncode == 0:
            tables = (proc.stdout or '').strip()
            self.stdout.write(f'  Bảng trong DB tạm: {tables}')

    def _drop_temp_db(self, test_db: str, *, ignore_missing: bool = False) -> None:
        cmd, env = self._psql_base()
        terminate = (
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{test_db}' AND pid <> pg_backend_pid();"
        )
        subprocess.run(
            cmd + ['-d', 'postgres', '-c', terminate],
            capture_output=True,
            check=False,
            env={**__import__('os').environ, **env},
        )
        proc = subprocess.run(
            cmd + ['-d', 'postgres', '-c', f'DROP DATABASE IF EXISTS "{test_db}";'],
            capture_output=True,
            check=False,
            env={**__import__('os').environ, **env},
        )
        if proc.returncode != 0 and not ignore_missing:
            err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace')[:1000]
            raise CommandError(err)
