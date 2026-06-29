"""Chạy nền các tác vụ áp dụng ACL NAS (tránh timeout Gunicorn 502)."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

_LOCK_STALE_SEC = 30 * 60
_LOG_PATH = Path('/tmp/nas_acl_apply.log')


def _lock_path(job_name: str) -> Path:
    return Path('/tmp') / f'nas_acl_job_{job_name}.lock'


def nas_acl_job_running(job_name: str) -> bool:
    lock = _lock_path(job_name)
    if not lock.exists():
        return False
    try:
        return (time.time() - lock.stat().st_mtime) < _LOCK_STALE_SEC
    except OSError:
        return False


def spawn_nas_acl_batch_job(command: str) -> bool:
    """
    Khởi chạy manage.py <command> nền.
    Trả False nếu job cùng loại đang chạy (lock < 30 phút).
    """
    if nas_acl_job_running(command):
        return False

    manage_py = Path(settings.BASE_DIR) / 'manage.py'
    lock = _lock_path(command)
    try:
        lock.touch()
    except OSError as exc:
        logger.warning('Cannot create NAS ACL job lock %s: %s', lock, exc)

    log_fp = open(_LOG_PATH, 'a', encoding='utf-8')  # noqa: SIM115
    log_fp.write(f'\n--- spawn {command} ---\n')
    log_fp.flush()

    subprocess.Popen(  # noqa: S603
        [sys.executable, str(manage_py), command],
        cwd=str(settings.BASE_DIR),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    logger.info('Spawned background NAS ACL job: %s', command)
    return True
