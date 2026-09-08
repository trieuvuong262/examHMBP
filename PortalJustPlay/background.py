"""Đưa việc nặng ra khỏi request — một cửa duy nhất cho toàn portal.

Vì sao cần lớp này thay vì gọi ``django_rq.enqueue`` trực tiếp:

  * **Không phải môi trường nào cũng có Redis.** Máy dev và test không chạy
    Redis; nếu gọi RQ trực tiếp thì code chết. Ở đây tự động rơi về chế độ
    chạy nền bằng thread (đúng như cách portal đang làm), hoặc chạy đồng bộ
    khi ``BACKGROUND_TASKS_EAGER`` bật (dùng cho test).
  * **Thay dần thread bằng RQ mà không phải sửa nghiệp vụ.** Các nơi đang dùng
    ``threading.Thread(daemon=True)`` chỉ cần đổi sang ``enqueue()``.

Vì sao thread là vấn đề: gunicorn worker bị restart (deploy, timeout, OOM) là
thread chết im lặng — job treo ở trạng thái "đang chạy" mãi mãi. RQ có tiến
trình worker riêng, job nằm trong Redis nên sống qua deploy và thấy được lỗi.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

QUEUE_DEFAULT = 'default'
QUEUE_NAS = 'nas'  # việc chạm NAS (chậm, hay treo) — tách để không chặn việc khác


def queue_available(queue_name: str = QUEUE_DEFAULT) -> bool:
    """Có Redis + django-rq dùng được không."""
    if getattr(settings, 'BACKGROUND_TASKS_EAGER', False):
        return False
    if not getattr(settings, 'RQ_QUEUES', None):
        return False
    try:
        import django_rq

        django_rq.get_connection(queue_name).ping()
        return True
    except Exception as exc:
        logger.warning('Hàng đợi %s không dùng được (%s) — chạy bằng thread.', queue_name, exc)
        return False


def _run_in_thread(func, args, kwargs):
    def _worker():
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception('Job nền %s thất bại', getattr(func, '__name__', func))
        finally:
            # Thread có connection DB riêng — phải đóng, nếu không sẽ rò kết nối
            connection.close()

    thread = threading.Thread(
        target=_worker,
        name=f'jp-bg-{getattr(func, "__name__", "task")}',
        daemon=True,
    )
    thread.start()
    return thread


def enqueue(
    func,
    *args,
    queue: str = QUEUE_DEFAULT,
    timeout: int = 900,
    description: str = '',
    **kwargs,
):
    """Đẩy một hàm sang chạy nền. Trả về RQ job, Thread, hoặc None (eager).

    ``func`` phải là hàm cấp module (import được bằng đường dẫn) để RQ
    serialize được — không dùng lambda hay closure.
    """
    if getattr(settings, 'BACKGROUND_TASKS_EAGER', False):
        # Test / lệnh quản trị: chạy ngay, lỗi nổi lên để thấy được
        func(*args, **kwargs)
        return None

    if queue_available(queue):
        import django_rq

        return django_rq.get_queue(queue).enqueue(
            func,
            *args,
            job_timeout=timeout,
            description=description or getattr(func, '__name__', ''),
            **kwargs,
        )

    return _run_in_thread(func, args, kwargs)


def queue_stats() -> list[dict]:
    """Số liệu hàng đợi cho màn hình quản trị."""
    if not getattr(settings, 'RQ_QUEUES', None):
        return []
    try:
        import django_rq
        from rq.registry import (
            FailedJobRegistry,
            FinishedJobRegistry,
            StartedJobRegistry,
        )
    except ImportError:
        return []

    rows = []
    for name in settings.RQ_QUEUES:
        try:
            q = django_rq.get_queue(name)
            rows.append({
                'name': name,
                'cho_xu_ly': q.count,
                'dang_chay': len(StartedJobRegistry(queue=q)),
                'da_xong': len(FinishedJobRegistry(queue=q)),
                'that_bai': len(FailedJobRegistry(queue=q)),
            })
        except Exception as exc:
            rows.append({'name': name, 'loi': str(exc)[:120]})
    return rows
