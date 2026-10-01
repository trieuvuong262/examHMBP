"""Backup database + source (+ media) lên NAS qua rclone."""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from nas_storage.nas_paths import default_nas_rclone_remote, nas_rclone_remote_path, rclone_listing_available

logger = logging.getLogger(__name__)

SCOPE_CODE = 'code'
SCOPE_DATA = 'data'
SCOPE_ALL = 'all'
SCOPE_LABELS = {
    SCOPE_CODE: 'mã nguồn',
    SCOPE_DATA: 'dữ liệu',
    SCOPE_ALL: 'toàn bộ',
}

_DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_RUN_RE = re.compile(r'^\d{8}-\d{6}-[A-Za-z0-9_-]{1,24}$')
_DB_NAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,63}$')
_CODE_SKIP_TOP = {
    '.env',
    '.git',
    'postgres_data',
    'staticfiles',
    'media',
    'node_modules',
    'venv',
    '.venv',
}


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


def _backup_ssh_enabled() -> bool:
    mode = (getattr(settings, 'NAS_BACKUP_TRANSPORT', 'auto') or 'auto').strip().lower()
    if mode == 'smb':
        return False
    if mode == 'ssh':
        return True
    # Trên VPS: binary SSH của host được mount vào container và đã có credential NAS.
    return os.path.isfile('/host/root/usr/bin/ssh') and os.path.isfile('/root/.nas-cred')


def _nas_ssh_password() -> str:
    cred = (getattr(settings, 'NAS_DSM_CRED_FILE', '') or '/root/.nas-cred').strip()
    if cred and os.path.isfile(cred):
        for line in open(cred, encoding='utf-8', errors='replace'):
            if line.startswith('password='):
                return line.split('=', 1)[1].strip()
    return (getattr(settings, 'NAS_DSM_PASSWORD', '') or '').strip()


def _ssh_bin() -> str:
    explicit = (getattr(settings, 'NAS_BACKUP_SSH_BIN', '') or '').strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    for cand in ('/usr/bin/ssh', '/host/root/usr/bin/ssh'):
        if os.path.isfile(cand):
            return cand
    return 'ssh'


def _backup_fs_path(remote_target: str) -> str:
    """synology:backup/2026-09-24/run/file → /volume1/backup/2026-09-24/run/file."""
    base = backup_rclone_base().rstrip('/')
    rel = remote_target
    if rel.startswith(base):
        rel = rel[len(base):]
    elif ':' in rel:
        rel = rel.split(':', 1)[1]
        share = base.split(':', 1)[-1].strip('/')
        if share and rel.startswith(share):
            rel = rel[len(share):]
    rel = rel.lstrip('/')
    if not rel or rel.startswith('..') or '/../' in f'/{rel}/':
        raise PortalBackupError(f'Đường backup không hợp lệ: {remote_target}')
    root = (getattr(settings, 'NAS_BACKUP_SSH_DIR', '/volume1/backup') or '/volume1/backup').rstrip('/')
    return f'{root}/{rel}'


def _ssh_cmd(remote_shell: str) -> tuple[list[str], dict]:
    host = (getattr(settings, 'NAS_BACKUP_SSH_HOST', '') or '192.168.40.252').strip()
    user = (getattr(settings, 'NAS_BACKUP_SSH_USER', '') or 'tailscale-justplay').strip()
    if not host or not user:
        raise PortalBackupError('Chưa cấu hình NAS_BACKUP_SSH_HOST / USER.')
    env = os.environ.copy()
    cmd = [
        _ssh_bin(),
        '-o', 'PreferredAuthentications=password',
        '-o', 'PubkeyAuthentication=no',
        '-o', 'NumberOfPasswordPrompts=1',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'UserKnownHostsFile=/tmp/nas-backup-known_hosts',
        '-o', 'ConnectTimeout=15',
        f'{user}@{host}',
        remote_shell,
    ]
    password = _nas_ssh_password()
    if not password:
        raise PortalBackupError('Không có mật khẩu SSH NAS (NAS_DSM_CRED_FILE).')
    askpass = '/tmp/nas-backup-askpass.sh'
    with open(askpass, 'w', encoding='utf-8') as fh:
        fh.write('#!/bin/sh\nprintf \'%s\\n\' "$NAS_BACKUP_SSH_PW"\n')
    os.chmod(askpass, 0o700)
    env['NAS_BACKUP_SSH_PW'] = password
    env['SSH_ASKPASS'] = askpass
    env['SSH_ASKPASS_REQUIRE'] = 'force'
    env['DISPLAY'] = env.get('DISPLAY') or 'none'
    return cmd, env


def _ssh_run(remote_shell: str, *, stdin_path: Path | None = None, timeout: int = 7200) -> subprocess.CompletedProcess:
    cmd, env = _ssh_cmd(remote_shell)
    stdin_fh = stdin_path.open('rb') if stdin_path else None
    try:
        return subprocess.run(
            cmd,
            stdin=stdin_fh,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalBackupError(f'Không upload được lên NAS qua SSH: {exc}') from exc
    finally:
        if stdin_fh:
            stdin_fh.close()


def ssh_copy_file(local_path: Path, remote_target: str) -> None:
    dest = _backup_fs_path(remote_target)
    parent = dest.rsplit('/', 1)[0]
    proc = _ssh_run(
        f'mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(dest)}',
        stdin_path=local_path,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace').strip()
        raise PortalBackupError(err or 'SSH upload thất bại.')


def rclone_copy_file(local_path: Path, remote_target: str) -> None:
    if _backup_ssh_enabled():
        ssh_copy_file(local_path, remote_target)
        return
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
    if days <= 0:
        return 0
    if _backup_ssh_enabled():
        root = (getattr(settings, 'NAS_BACKUP_SSH_DIR', '/volume1/backup') or '/volume1/backup').rstrip('/')
        # Chỉ file nằm trong thư mục ngày /volume1/backup/YYYY-MM-DD/...
        script = (
            f'find {shlex.quote(root)} -mindepth 2 -type f -mtime +{int(days)} -delete; '
            f'find {shlex.quote(root)} -mindepth 1 -type d -empty -delete'
        )
        try:
            proc = _ssh_run(script, timeout=3600)
        except PortalBackupError:
            return 0
        return 0 if proc.returncode != 0 else 1
    if not rclone_listing_available():
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


def portal_backup_busy() -> bool:
    from audit.models import PortalBackupJob

    return PortalBackupJob.objects.filter(
        status__in=(PortalBackupJob.STATUS_PENDING, PortalBackupJob.STATUS_RUNNING),
    ).exists()


def run_portal_backup(*, job_id: int | None = None, trigger: str = 'scheduled', user=None) -> dict:
    from audit.models import PortalBackupJob

    active = PortalBackupJob.objects.filter(
        status__in=(PortalBackupJob.STATUS_PENDING, PortalBackupJob.STATUS_RUNNING),
    )
    if job_id:
        active = active.exclude(pk=job_id)
    if active.exists():
        raise PortalBackupError('Đang có một tiến trình backup hoặc khôi phục khác.')

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

    if portal_backup_busy():
        raise PortalBackupError('Đang có backup hoặc khôi phục khác — vui lòng đợi hoàn tất.')

    job = PortalBackupJob.objects.create(
        trigger=trigger,
        status=PortalBackupJob.STATUS_PENDING,
        started_by=user,
    )

    from PortalJustPlay.background import QUEUE_NAS, enqueue

    enqueue(
        run_portal_backup_safe, job.pk, trigger, user.pk if user else None,
        queue=QUEUE_NAS, timeout=7200, description=f'Backup portal #{job.pk}',
    )
    return job


def run_portal_backup_safe(job_id: int, trigger: str, user_id: int | None) -> None:
    """Wrapper cho job nền — backup ghi ra NAS nên xếp vào hàng đợi 'nas'."""
    from django.contrib.auth.models import User
    from django.db import connection

    from audit.models import PortalBackupJob

    user = User.objects.filter(pk=user_id).first() if user_id else None
    try:
        run_portal_backup(job_id=job_id, trigger=trigger, user=user)
    except PortalBackupError:
        pass
    except Exception as exc:
        PortalBackupJob.objects.filter(pk=job_id).update(
            status=PortalBackupJob.STATUS_FAILED,
            finished_at=timezone.now(),
            message=str(exc)[:2000],
        )
    finally:
        connection.close()


def latest_backup_job():
    from audit.models import PortalBackupJob

    return (
        PortalBackupJob.objects.filter(kind=PortalBackupJob.KIND_BACKUP)
        .order_by('-started_at', '-created_at')
        .first()
    )


def latest_restore_job():
    from audit.models import PortalBackupJob

    return (
        PortalBackupJob.objects.filter(kind=PortalBackupJob.KIND_RESTORE)
        .order_by('-started_at', '-created_at')
        .first()
    )


def parse_snapshot_rel(rel: str) -> tuple[str, str] | None:
    rel = (rel or '').strip().strip('/')
    parts = [part for part in rel.split('/') if part]
    if len(parts) != 2:
        return None
    day, run_id = parts
    if not _DAY_RE.fullmatch(day) or not _RUN_RE.fullmatch(run_id):
        return None
    if run_id[:8] != day.replace('-', ''):
        return None
    return day, run_id


def snapshot_remote_path(day: str, run_id: str) -> str:
    parsed = parse_snapshot_rel(f'{day}/{run_id}')
    if not parsed:
        raise PortalBackupError('Ngày hoặc mã file backup không hợp lệ.')
    day, run_id = parsed
    return f'{backup_rclone_base().rstrip("/")}/{day}/{run_id}'


def group_backup_snapshots(rels: list[str]) -> list[dict]:
    found: dict[str, dict[str, dict]] = {}
    for rel in rels:
        parsed = parse_snapshot_rel(rel)
        if not parsed:
            continue
        day, run_id = parsed
        hhmm = f'{run_id[9:11]}:{run_id[11:13]}'
        suffix = run_id.rsplit('-', 1)[-1]
        kind = {'sch': 'Tự động', 'man': 'Thủ công'}.get(suffix, suffix)
        found.setdefault(day, {})[run_id] = {
            'run_id': run_id,
            'time': hhmm,
            'kind': kind,
            'label': f'{hhmm} · {kind}',
        }
    days = []
    for day in sorted(found, reverse=True):
        runs = [found[day][key] for key in sorted(found[day], reverse=True)]
        year, month, day_num = day.split('-')
        days.append({
            'day': day,
            'label': f'{day_num}/{month}/{year}',
            'runs': runs,
        })
    return days


def _ssh_text(remote_shell: str, *, timeout: int = 60) -> str:
    proc = _ssh_run(remote_shell, timeout=timeout)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace').strip()
        raise PortalBackupError(err or 'Không đọc được thư mục backup trên NAS.')
    return (proc.stdout or b'').decode('utf-8', errors='replace')


def _list_snapshot_rels() -> list[str]:
    if _backup_ssh_enabled():
        root = (getattr(settings, 'NAS_BACKUP_SSH_DIR', '/volume1/backup') or '/volume1/backup').rstrip('/')
        text = _ssh_text(f'find {shlex.quote(root)} -mindepth 2 -maxdepth 2 -type d', timeout=45)
        prefix = f'{root}/'
        rels = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(prefix):
                rels.append(line[len(prefix):])
        return rels
    if not rclone_listing_available():
        raise PortalBackupError('Không kết nối được NAS để đọc danh sách backup.')
    base = backup_rclone_base()
    try:
        proc = subprocess.run(
            ['rclone', 'lsf', base, '--dirs-only', '--recursive', '--max-depth', '2'],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalBackupError(f'Không đọc được danh sách backup: {exc}') from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise PortalBackupError(err or 'rclone lsf thất bại.')
    return [line.strip().strip('/') for line in (proc.stdout or '').splitlines() if line.strip()]


def list_backup_snapshots() -> list[dict]:
    from django.core.cache import cache

    cache_key = 'portal_backup_snapshots_v1'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    days = group_backup_snapshots(_list_snapshot_rels())
    cache.set(cache_key, days, 30)
    return days


def snapshots_from_jobs(limit: int = 60) -> list[dict]:
    from audit.models import PortalBackupJob

    rows = (
        PortalBackupJob.objects.filter(
            kind=PortalBackupJob.KIND_BACKUP,
            status=PortalBackupJob.STATUS_SUCCESS,
        )
        .exclude(remote_path='')
        .order_by('-started_at', '-created_at')[:limit]
    )
    rels = []
    for row in rows:
        parts = [part for part in (row.remote_path or '').rstrip('/').split('/') if part]
        if len(parts) >= 2:
            rels.append(f'{parts[-2]}/{parts[-1]}')
    return group_backup_snapshots(rels)


def list_remote_file_names(remote_dir: str) -> list[str]:
    if _backup_ssh_enabled():
        dest = _backup_fs_path(remote_dir)
        text = _ssh_text(f'ls -1 {shlex.quote(dest)}', timeout=45)
        names = []
        for line in text.splitlines():
            name = line.strip()
            if name and '/' not in name and name not in ('.', '..'):
                names.append(name)
        return names
    if not rclone_listing_available():
        raise PortalBackupError('Không kết nối được NAS.')
    try:
        proc = subprocess.run(
            ['rclone', 'lsf', remote_dir, '--files-only'],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalBackupError(f'Không đọc được file backup: {exc}') from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise PortalBackupError(err or 'Không đọc được file backup.')
    return [line.strip() for line in (proc.stdout or '').splitlines() if line.strip() and '/' not in line.strip()]


def files_for_scope(names: list[str], scope: str) -> list[str]:
    wanted: list[str] = []
    if scope in (SCOPE_CODE, SCOPE_ALL):
        wanted.extend(sorted(
            name for name in names
            if name.startswith('source-') and name.endswith('.tar.gz')
        ))
    if scope in (SCOPE_DATA, SCOPE_ALL):
        if 'database.sql.gz' in names:
            wanted.append('database.sql.gz')
        if 'media.tar.gz' in names:
            wanted.append('media.tar.gz')
    return wanted


def download_remote_file(remote_target: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if local_path.exists():
        local_path.unlink()
    if _backup_ssh_enabled():
        src = _backup_fs_path(remote_target)
        cmd, env = _ssh_cmd(f'cat {shlex.quote(src)}')
        with local_path.open('wb') as out:
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=out,
                    stderr=subprocess.PIPE,
                    timeout=7200,
                    check=False,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                local_path.unlink(missing_ok=True)
                raise PortalBackupError(f'Không tải được file backup: {exc}') from exc
        if proc.returncode != 0 or not local_path.is_file() or local_path.stat().st_size == 0:
            local_path.unlink(missing_ok=True)
            err = (proc.stderr or b'').decode('utf-8', errors='replace').strip()
            raise PortalBackupError(err or 'Không tải được file backup.')
        return
    if not rclone_listing_available():
        raise PortalBackupError('rclone chưa cấu hình trên server.')
    try:
        proc = subprocess.run(
            ['rclone', 'copyto', remote_target, str(local_path)],
            capture_output=True,
            text=True,
            timeout=7200,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        local_path.unlink(missing_ok=True)
        raise PortalBackupError(f'Không tải được file backup: {exc}') from exc
    if proc.returncode != 0 or not local_path.is_file() or local_path.stat().st_size == 0:
        local_path.unlink(missing_ok=True)
        err = (proc.stderr or proc.stdout or '').strip()
        raise PortalBackupError(err or 'rclone copyto thất bại.')


def _code_restore_dir() -> Path:
    raw = getattr(settings, 'PORTAL_RESTORE_CODE_DIR', '/backup-source') or '/backup-source'
    path = Path(raw)
    if not path.is_dir():
        raise PortalBackupError(f'Không thấy thư mục mã nguồn {path}.')
    if not os.access(path, os.W_OK):
        raise PortalBackupError(
            'Thư mục mã nguồn đang chỉ đọc. Worker cần gắn HOST_PROJECT_DIR ở chế độ ghi rồi khôi phục lại.'
        )
    return path.resolve()


def _safe_target(dest_root: Path, rel: str) -> Path:
    target = (dest_root / rel).resolve()
    if target != dest_root and not str(target).startswith(str(dest_root) + os.sep):
        raise PortalBackupError(f'Đường dẫn không an toàn trong file backup: {rel}')
    return target


def extract_source_tar(tar_path: Path, dest_root: Path, prefix: str, *, skip_protected: bool = False) -> int:
    dest_root = dest_root.resolve()
    prefix = prefix.strip('/')
    head = f'{prefix}/'
    count = 0
    with tarfile.open(tar_path, 'r:gz') as tar:
        for member in tar.getmembers():
            name = member.name.replace('\\', '/').lstrip('./')
            if not name or name.startswith('/') or any(part == '..' for part in name.split('/')):
                raise PortalBackupError(f'File backup chứa đường dẫn không an toàn: {member.name}')
            if name == prefix or not name.startswith(head):
                continue
            rel = name[len(head):]
            if not rel:
                continue
            top = rel.split('/', 1)[0]
            if skip_protected and (top in _CODE_SKIP_TOP or top.startswith('.env')):
                continue
            target = _safe_target(dest_root, rel)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isreg():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            if src is None:
                continue
            with target.open('wb') as out:
                shutil.copyfileobj(src, out)
            mode = member.mode & 0o777
            if mode:
                try:
                    os.chmod(target, mode)
                except OSError:
                    pass
            count += 1
    if count == 0:
        raise PortalBackupError(f'{tar_path.name} không có file để khôi phục.')
    return count


def restore_code_from_workdir(work: Path) -> str:
    dest = _code_restore_dir()
    host_tar = work / 'source-backup-source.tar.gz'
    app_tar = work / 'source-app.tar.gz'
    if host_tar.is_file():
        count = extract_source_tar(host_tar, dest, 'backup-source', skip_protected=True)
        return f'Đã ghi {count} file mã nguồn vào {dest}. Không ghi đè .env và .git. Cần deploy để portal chạy code mới.'
    if app_tar.is_file():
        count = extract_source_tar(app_tar, dest, 'app', skip_protected=True)
        return f'Đã ghi {count} file mã nguồn vào {dest}. Không ghi đè .env và .git. Cần deploy để portal chạy code mới.'
    others = sorted(work.glob('source-*.tar.gz'))
    if not others:
        raise PortalBackupError('Backup không có gói mã nguồn.')
    tar_path = others[0]
    label = tar_path.name[len('source-'):-len('.tar.gz')]
    count = extract_source_tar(tar_path, dest, label, skip_protected=True)
    return f'Đã ghi {count} file mã nguồn vào {dest}. Cần deploy để portal chạy code mới.'


def restore_media_archive(tar_path: Path) -> str:
    media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '')
    if not media_root.is_dir():
        raise PortalBackupError('Không thấy thư mục media.')
    if not os.access(media_root, os.W_OK):
        raise PortalBackupError('Không ghi được vào thư mục media.')
    staging = Path(tempfile.mkdtemp(prefix='portal-media-restore-'))
    try:
        count = extract_source_tar(tar_path, staging, 'media')
        for child in list(media_root.iterdir()):
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        for child in staging.iterdir():
            shutil.move(str(child), str(media_root / child.name))
        return f'Đã khôi phục media ({count} file).'
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _skip_sql_line(line: bytes) -> bool:
    stripped = line.strip()
    if stripped in (b'CREATE SCHEMA public;', b'CREATE SCHEMA IF NOT EXISTS public;'):
        return True
    return stripped.startswith((
        b'SET transaction_timeout',
        b'SET idle_in_transaction_session_timeout',
    ))


def _psql_cmd(database: str, *, stop_on_error: bool) -> tuple[list[str], dict]:
    db = settings.DATABASES['default']
    env = os.environ.copy()
    if db.get('PASSWORD'):
        env['PGPASSWORD'] = str(db['PASSWORD'])
    cmd = [
        'psql',
        '-h', str(db.get('HOST') or 'localhost'),
        '-p', str(db.get('PORT') or '5432'),
        '-U', str(db.get('USER') or 'postgres'),
        '-d', database,
    ]
    if stop_on_error:
        cmd.extend(['-v', 'ON_ERROR_STOP=1'])
    return cmd, env


def restore_database_dump(sql_gz: Path, *, on_replaced=None) -> str:
    if not sql_gz.is_file() or sql_gz.stat().st_size < 32:
        raise PortalBackupError('Thiếu database.sql.gz.')
    with gzip.open(sql_gz, 'rb') as gz:
        head = gz.read(8192)
    if b'PostgreSQL' not in head and b'CREATE TABLE' not in head and b'COPY ' not in head:
        raise PortalBackupError('database.sql.gz không phải bản dump PostgreSQL.')

    db = settings.DATABASES['default']
    name = str(db.get('NAME') or '')
    if not _DB_NAME_RE.fullmatch(name):
        raise PortalBackupError('Tên database không hỗ trợ khôi phục tự động.')

    from django.db import connection

    connection.close()
    cmd, env = _psql_cmd(name, stop_on_error=False)
    subprocess.run(
        cmd,
        input=(
            b'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
            b'WHERE datname = current_database() AND pid <> pg_backend_pid();\n'
        ),
        capture_output=True,
        timeout=120,
        check=False,
        env=env,
    )
    drop_cmd, drop_env = _psql_cmd(name, stop_on_error=True)
    proc = subprocess.run(
        drop_cmd,
        input=(
            b'DROP SCHEMA IF EXISTS public CASCADE;\n'
            b'CREATE SCHEMA public;\n'
            b'GRANT ALL ON SCHEMA public TO PUBLIC;\n'
        ),
        capture_output=True,
        timeout=600,
        check=False,
        env=drop_env,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b'').decode('utf-8', errors='replace')[:2000]
        raise PortalBackupError(f'Không xóa được dữ liệu hiện tại: {err}')
    if on_replaced is not None:
        on_replaced()

    load_cmd, load_env = _psql_cmd(name, stop_on_error=True)
    loader = subprocess.Popen(
        load_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=load_env,
    )
    assert loader.stdin is not None
    try:
        with gzip.open(sql_gz, 'rb') as gz:
            for line in gz:
                if _skip_sql_line(line):
                    continue
                loader.stdin.write(line)
        stdout, stderr = loader.communicate(timeout=7200)
    except BrokenPipeError:
        stdout, stderr = loader.communicate(timeout=120)
    except subprocess.TimeoutExpired as exc:
        loader.kill()
        loader.communicate()
        raise PortalBackupError('Khôi phục database quá thời gian.') from exc
    except Exception:
        loader.kill()
        loader.communicate()
        raise
    if loader.returncode != 0:
        err = (stderr or stdout or b'').decode('utf-8', errors='replace')[:2000]
        raise PortalBackupError(f'Khôi phục database thất bại: {err}')
    connection.close()
    return 'Đã khôi phục database.'


def _migrate_after_restore() -> None:
    from django.core.management import call_command
    from django.db import connection

    connection.close()
    call_command('migrate', '--noinput', verbosity=0)
    connection.close()


def _finish_restore_job(*, job_id: int, user, remote_path: str, scope: str, started_at, message: str, db_replaced: bool) -> None:
    from audit.models import PortalBackupJob

    if db_replaced and scope != SCOPE_DATA:
        # Toàn bộ: giữ schema đúng bản backup để khớp mã nguồn vừa ghi ra.
        # Bản backup cũ chưa có cột kind/scope thì bỏ qua việc ghi nhật ký.
        try:
            PortalBackupJob.objects.create(
                kind=PortalBackupJob.KIND_RESTORE,
                scope=scope,
                trigger=PortalBackupJob.TRIGGER_MANUAL,
                status=PortalBackupJob.STATUS_SUCCESS,
                started_by=user,
                started_at=started_at,
                finished_at=timezone.now(),
                remote_path=remote_path,
                message=message[:2000],
            )
        except Exception:
            logger.exception('Đã khôi phục nhưng không ghi được nhật ký trên schema của bản backup.')
        return
    if db_replaced:
        status = PortalBackupJob.STATUS_SUCCESS
        try:
            _migrate_after_restore()
        except Exception as exc:
            logger.exception('migrate sau khôi phục database')
            status = PortalBackupJob.STATUS_FAILED
            message = f'{message} Migrate sau khôi phục lỗi: {exc}'[:2000]
        PortalBackupJob.objects.create(
            kind=PortalBackupJob.KIND_RESTORE,
            scope=scope,
            trigger=PortalBackupJob.TRIGGER_MANUAL,
            status=status,
            started_by=user,
            started_at=started_at,
            finished_at=timezone.now(),
            remote_path=remote_path,
            message=message[:2000],
        )
        return
    PortalBackupJob.objects.filter(pk=job_id).update(
        status=PortalBackupJob.STATUS_SUCCESS,
        finished_at=timezone.now(),
        message=message[:2000],
    )


def _mark_restore_failed(job_id: int, message: str, *, db_replaced: bool, scope: str, user, remote_path: str) -> None:
    from django.db import connection

    from audit.models import PortalBackupJob

    connection.close()
    text = message[:2000]
    try:
        if db_replaced and scope == SCOPE_DATA:
            try:
                _migrate_after_restore()
            except Exception:
                logger.exception('migrate sau khôi phục database thất bại')
        if db_replaced:
            PortalBackupJob.objects.create(
                kind=PortalBackupJob.KIND_RESTORE,
                scope=scope,
                trigger=PortalBackupJob.TRIGGER_MANUAL,
                status=PortalBackupJob.STATUS_FAILED,
                started_by=user,
                started_at=timezone.now(),
                finished_at=timezone.now(),
                remote_path=remote_path,
                message=text,
            )
            return
        updated = PortalBackupJob.objects.filter(pk=job_id).update(
            status=PortalBackupJob.STATUS_FAILED,
            finished_at=timezone.now(),
            message=text,
        )
        if not updated:
            PortalBackupJob.objects.create(
                kind=PortalBackupJob.KIND_RESTORE,
                scope=scope,
                trigger=PortalBackupJob.TRIGGER_MANUAL,
                status=PortalBackupJob.STATUS_FAILED,
                started_by=user,
                finished_at=timezone.now(),
                remote_path=remote_path,
                message=text,
            )
    except Exception:
        logger.exception('Không ghi được trạng thái khôi phục thất bại')


def assert_snapshot_restorable(day: str, run_id: str, scope: str) -> str:
    if scope not in SCOPE_LABELS:
        raise PortalBackupError('Chọn khôi phục mã nguồn, dữ liệu hoặc toàn bộ.')
    remote = snapshot_remote_path(day, run_id)
    names = list_remote_file_names(remote)
    if scope in (SCOPE_DATA, SCOPE_ALL) and 'database.sql.gz' not in names:
        raise PortalBackupError('Bản backup này không có database.')
    if scope in (SCOPE_CODE, SCOPE_ALL) and not any(
        name.startswith('source-') and name.endswith('.tar.gz') for name in names
    ):
        raise PortalBackupError('Bản backup này không có mã nguồn.')
    if not files_for_scope(names, scope):
        raise PortalBackupError('Không có file phù hợp để khôi phục.')
    return remote


def start_restore_async(*, day: str, run_id: str, scope: str, user):
    from audit.models import PortalBackupJob

    if portal_backup_busy():
        raise PortalBackupError('Đang có backup hoặc khôi phục khác — vui lòng đợi hoàn tất.')
    remote = assert_snapshot_restorable(day, run_id, scope)
    job = PortalBackupJob.objects.create(
        kind=PortalBackupJob.KIND_RESTORE,
        scope=scope,
        trigger=PortalBackupJob.TRIGGER_MANUAL,
        status=PortalBackupJob.STATUS_PENDING,
        started_by=user,
        remote_path=remote,
        message=f'Chờ khôi phục {SCOPE_LABELS[scope]}.',
    )
    from PortalJustPlay.background import QUEUE_NAS, enqueue

    enqueue(
        run_portal_restore_safe,
        job.pk,
        user.pk if user else None,
        queue=QUEUE_NAS,
        timeout=7200,
        description=f'Khôi phục portal #{job.pk}',
    )
    return job


def run_portal_restore(*, job_id: int, user=None) -> None:
    from audit.models import PortalBackupJob

    job = PortalBackupJob.objects.get(pk=job_id)
    scope = job.scope if job.scope in SCOPE_LABELS else ''
    if not scope:
        _mark_restore_failed(
            job_id,
            'Thiếu phạm vi khôi phục.',
            db_replaced=False,
            scope=job.scope,
            user=user,
            remote_path=job.remote_path,
        )
        raise PortalBackupError('Thiếu phạm vi khôi phục.')

    job.status = PortalBackupJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at'])
    started_at = job.started_at
    remote = job.remote_path
    state = {'db_replaced': False}
    parts: list[str] = []
    work_dir = Path(tempfile.mkdtemp(prefix='portal-restore-'))
    try:
        if PortalBackupJob.objects.filter(
            status__in=(PortalBackupJob.STATUS_PENDING, PortalBackupJob.STATUS_RUNNING),
        ).exclude(pk=job_id).exists():
            raise PortalBackupError('Đang có một tiến trình backup hoặc khôi phục khác.')
        names = list_remote_file_names(remote)
        wanted = files_for_scope(names, scope)
        if not wanted:
            raise PortalBackupError('Backup không có file phù hợp với lựa chọn.')
        for name in wanted:
            download_remote_file(f'{remote}/{name}', work_dir / name)

        if scope in (SCOPE_DATA, SCOPE_ALL):
            def _mark_db_replaced():
                state['db_replaced'] = True

            parts.append(restore_database_dump(work_dir / 'database.sql.gz', on_replaced=_mark_db_replaced))
            media_tar = work_dir / 'media.tar.gz'
            if media_tar.is_file():
                parts.append(restore_media_archive(media_tar))
            else:
                parts.append('Backup không có media.')
        if scope in (SCOPE_CODE, SCOPE_ALL):
            parts.append(restore_code_from_workdir(work_dir))
        if scope == SCOPE_ALL:
            parts.append('Cần deploy ngay để code đang chạy khớp database vừa khôi phục.')
        _finish_restore_job(
            job_id=job_id,
            user=user,
            remote_path=remote,
            scope=scope,
            started_at=started_at,
            message=' '.join(parts),
            db_replaced=state['db_replaced'],
        )
    except Exception as exc:
        done = ' '.join(parts).strip()
        message = f'{done} Lỗi: {exc}'.strip() if done else str(exc)
        if state['db_replaced'] and 'database' not in done.lower():
            message = f'Database đã được thay bằng bản backup. {message}'
        _mark_restore_failed(
            job_id,
            message,
            db_replaced=state['db_replaced'],
            scope=scope,
            user=user,
            remote_path=remote,
        )
        if not isinstance(exc, PortalBackupError):
            raise PortalBackupError(str(exc)) from exc
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_portal_restore_safe(job_id: int, user_id: int | None) -> None:
    from django.contrib.auth.models import User
    from django.db import connection

    user = User.objects.filter(pk=user_id).first() if user_id else None
    try:
        run_portal_restore(job_id=job_id, user=user)
    except PortalBackupError:
        pass
    except Exception as exc:
        logger.exception('Khôi phục portal thất bại')
        try:
            from audit.models import PortalBackupJob

            job = PortalBackupJob.objects.filter(pk=job_id).first()
            _mark_restore_failed(
                job_id,
                str(exc),
                db_replaced=False,
                scope=job.scope if job else '',
                user=user,
                remote_path=job.remote_path if job else '',
            )
        except Exception:
            logger.exception('Không ghi được lỗi khôi phục')
    finally:
        connection.close()
