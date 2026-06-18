"""Backup database + source (+ media) lên NAS qua rclone."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from nas_storage.nas_paths import default_nas_rclone_remote, nas_rclone_remote_path, rclone_listing_available


class PortalBackupError(Exception):
    pass


@dataclass
class BackupArtifact:
    name: str
    local_path: Path
    remote_path: str
    size_bytes: int


def _rclone_env() -> dict:
    env = os.environ.copy()
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and os.path.isfile(config):
        env['RCLONE_CONFIG'] = config
    return env


def backup_rclone_base() -> str:
    """Gốc trên NAS — mặc định ``synology:backup`` (thư mục/share backup ở gốc NAS)."""
    dedicated = (getattr(settings, 'NAS_BACKUP_RCLONE_REMOTE', '') or '').strip().rstrip('/')
    rel = (getattr(settings, 'NAS_BACKUP_REL_PATH', '') or '').strip('/')
    if dedicated:
        return nas_rclone_remote_path(dedicated, rel) if rel else dedicated
    base = default_nas_rclone_remote()
    return nas_rclone_remote_path(base, rel or 'backup')


def backup_remote_dir(stamp: str, run_id: str) -> str:
    """Đường dẫn remote: synology:backup/2026-05-28/20260528-020000-sch/."""
    base = backup_rclone_base()
    if len(stamp) >= 8 and stamp[0:8].isdigit():
        day = f'{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}'
    else:
        day = timezone.localdate().isoformat()
    return f'{base}/{day}/{run_id}'


def backup_source_dirs() -> list[Path]:
    raw = getattr(settings, 'PORTAL_BACKUP_SOURCE_DIRS', '/app')
    dirs: list[Path] = []
    for part in str(raw).split(','):
        part = part.strip()
        if not part:
            continue
        path = Path(part)
        if path.is_dir():
            dirs.append(path.resolve())
    return dirs


def _tar_exclude_names() -> set[str]:
    return {
        '__pycache__',
        '.pytest_cache',
        'node_modules',
        '.venv',
        'venv',
        'staticfiles',
        '.git',
        'postgres_data',
        'backups',
    }


def create_source_archive(src_dir: Path, dest_tar: Path, *, label: str) -> None:
    dest_tar.parent.mkdir(parents=True, exist_ok=True)
    excludes = _tar_exclude_names()
    with tarfile.open(dest_tar, 'w:gz') as tar:
        for root, dirnames, filenames in os.walk(src_dir):
            dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith('.')]
            root_path = Path(root)
            for name in filenames:
                if name.endswith(('.pyc', '.pyo')):
                    continue
                full = root_path / name
                try:
                    arcname = f'{label}/{full.relative_to(src_dir).as_posix()}'
                except ValueError:
                    continue
                tar.add(full, arcname=arcname, recursive=False)


def sanitize_pg_dump_sql(sql: bytes) -> bytes:
    """Bỏ SET chỉ có trên PG16+ để restore được lên PostgreSQL 15."""
    skip_prefixes = (
        b'SET transaction_timeout',
        b'SET idle_in_transaction_session_timeout',
    )
    return b''.join(
        line for line in sql.splitlines(keepends=True)
        if not any(line.startswith(prefix) for prefix in skip_prefixes)
    )


def create_database_dump(dest_gz: Path) -> None:
    db = settings.DATABASES['default']
    dest_gz.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if db.get('PASSWORD'):
        env['PGPASSWORD'] = str(db['PASSWORD'])
    cmd = [
        'pg_dump',
        '-h', str(db.get('HOST') or 'localhost'),
        '-p', str(db.get('PORT') or '5432'),
        '-U', str(db.get('USER') or 'postgres'),
        '-d', str(db.get('NAME') or 'postgres'),
        '--no-owner',
        '--no-acl',
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            timeout=3600,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalBackupError(f'pg_dump thất bại: {exc}') from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace')[:2000]
        raise PortalBackupError(f'pg_dump lỗi: {err}')
    with gzip.open(dest_gz, 'wb', compresslevel=6) as gz:
        gz.write(sanitize_pg_dump_sql(proc.stdout))


def rclone_copy_file(local_path: Path, remote_target: str) -> None:
    if not rclone_listing_available():
        raise PortalBackupError('rclone chưa cấu hình trên server.')
    try:
        proc = subprocess.run(
            ['rclone', 'copyto', str(local_path), remote_target],
            capture_output=True,
            text=True,
            timeout=7200,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalBackupError(f'Không upload được lên NAS: {exc}') from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise PortalBackupError(err or 'rclone copyto thất bại.')


def prune_old_remote_backups() -> int:
    """Xóa backup NAS cũ hơn NAS_BACKUP_RETENTION_DAYS (chỉ dưới backup_rclone_base)."""
    days = int(getattr(settings, 'NAS_BACKUP_RETENTION_DAYS', 30))
    if days <= 0 or not rclone_listing_available():
        return 0
    target = backup_rclone_base()
    try:
        proc = subprocess.run(
            ['rclone', 'delete', target, '--min-age', f'{days}d'],
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return 0 if proc.returncode != 0 else 1


def run_portal_backup(*, job_id: int | None = None, trigger: str = 'scheduled', user=None) -> dict:
    from audit.models import PortalBackupJob

    if PortalBackupJob.objects.filter(status=PortalBackupJob.STATUS_RUNNING).exists():
        raise PortalBackupError('Đang có một tiến trình backup khác.')

    stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
    run_id = f'{stamp}-{trigger[:3]}'

    if job_id:
        job = PortalBackupJob.objects.get(pk=job_id)
        job.status = PortalBackupJob.STATUS_RUNNING
        job.started_at = timezone.now()
        job.remote_path = backup_remote_dir(stamp, run_id)
        job.save(update_fields=['status', 'started_at', 'remote_path'])
    else:
        job = PortalBackupJob.objects.create(
            trigger=trigger,
            status=PortalBackupJob.STATUS_RUNNING,
            started_by=user,
            started_at=timezone.now(),
            remote_path=backup_remote_dir(stamp, run_id),
        )

    work_dir = Path(tempfile.mkdtemp(prefix='portal-backup-'))
    artifacts: list[BackupArtifact] = []
    remote_base = job.remote_path

    try:
        db_file = work_dir / 'database.sql.gz'
        create_database_dump(db_file)
        remote_db = f'{remote_base}/database.sql.gz'
        rclone_copy_file(db_file, remote_db)
        artifacts.append(BackupArtifact('database.sql.gz', db_file, remote_db, db_file.stat().st_size))

        for idx, src in enumerate(backup_source_dirs()):
            label = src.name.replace('/', '_') or f'source{idx}'
            tar_path = work_dir / f'source-{label}.tar.gz'
            create_source_archive(src, tar_path, label=label)
            remote_tar = f'{remote_base}/source-{label}.tar.gz'
            rclone_copy_file(tar_path, remote_tar)
            artifacts.append(BackupArtifact(tar_path.name, tar_path, remote_tar, tar_path.stat().st_size))

        media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '')
        if getattr(settings, 'PORTAL_BACKUP_INCLUDE_MEDIA', True) and media_root.is_dir():
            has_files = any(media_root.rglob('*'))
            if has_files:
                media_tar = work_dir / 'media.tar.gz'
                create_source_archive(media_root, media_tar, label='media')
                remote_media = f'{remote_base}/media.tar.gz'
                rclone_copy_file(media_tar, remote_media)
                artifacts.append(BackupArtifact('media.tar.gz', media_tar, remote_media, media_tar.stat().st_size))

        manifest = {
            'created_at': timezone.now().isoformat(),
            'trigger': trigger,
            'triggered_by': getattr(user, 'username', None),
            'remote_path': remote_base,
            'artifacts': [
                {'name': a.name, 'remote': a.remote_path, 'size_bytes': a.size_bytes}
                for a in artifacts
            ],
        }
        manifest_path = work_dir / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        remote_manifest = f'{remote_base}/manifest.json'
        rclone_copy_file(manifest_path, remote_manifest)

        prune_old_remote_backups()

        job.status = PortalBackupJob.STATUS_SUCCESS
        job.finished_at = timezone.now()
        job.message = f'Đã backup {len(artifacts)} gói lên NAS.'
        job.artifacts = manifest['artifacts']
        job.save(update_fields=['status', 'finished_at', 'message', 'artifacts'])
        return manifest

    except Exception as exc:
        job.status = PortalBackupJob.STATUS_FAILED
        job.finished_at = timezone.now()
        job.message = str(exc)[:2000]
        job.save(update_fields=['status', 'finished_at', 'message'])
        raise

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def start_backup_async(*, trigger: str, user) -> PortalBackupJob:
    import threading

    from audit.models import PortalBackupJob

    if PortalBackupJob.objects.filter(status=PortalBackupJob.STATUS_RUNNING).exists():
        raise PortalBackupError('Đang có backup khác — vui lòng đợi hoàn tất.')

    job = PortalBackupJob.objects.create(
        trigger=trigger,
        status=PortalBackupJob.STATUS_PENDING,
        started_by=user,
    )

    def _worker():
        from django.db import connection

        try:
            run_portal_backup(job_id=job.pk, trigger=trigger, user=user)
        except PortalBackupError:
            pass
        except Exception as exc:
            PortalBackupJob.objects.filter(pk=job.pk).update(
                status=PortalBackupJob.STATUS_FAILED,
                finished_at=timezone.now(),
                message=str(exc)[:2000],
            )
        finally:
            connection.close()

    threading.Thread(target=_worker, daemon=True).start()
    return job


def latest_backup_job():
    from audit.models import PortalBackupJob

    return PortalBackupJob.objects.order_by('-started_at', '-created_at').first()
