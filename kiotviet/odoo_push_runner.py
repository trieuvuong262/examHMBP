"""Chạy job đẩy sản phẩm KiotViet → Odoo nền (thread) với tiến độ.

Tái dùng model KvSyncJob làm bản ghi tiến độ (entities=['odoo_push']).
"""

from __future__ import annotations

import logging
import threading

from django.db import connection
from django.utils import timezone

from .models import KvSyncJob
from .odoo_bridge import odoo_ready, push_products

logger = logging.getLogger(__name__)

ODOO_PUSH_MARKER = 'odoo_push'


class OdooPushRunnerError(Exception):
    pass


def run_odoo_push_job(*, job_id: int, options: dict) -> None:
    job = KvSyncJob.objects.get(pk=job_id)
    job.status = KvSyncJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.progress_percent = 1
    job.current_entity = ODOO_PUSH_MARKER
    job.message = 'Đang khởi động đẩy dữ liệu sang Odoo…'
    job.save(update_fields=['status', 'started_at', 'progress_percent', 'current_entity', 'message'])

    if not odoo_ready():
        job.status = KvSyncJob.STATUS_FAILED
        job.finished_at = timezone.now()
        job.progress_percent = 100
        job.message = 'Odoo chưa cấu hình (ODOO_URL/DB/API_USER/PASSWORD).'
        job.save(update_fields=['status', 'finished_at', 'progress_percent', 'message'])
        return

    def on_progress(msg: str, pct=None) -> None:
        fields = {'message': msg}
        if pct is not None:
            fields['progress_percent'] = max(1, min(99, int(pct)))
        KvSyncJob.objects.filter(pk=job_id).update(**fields)

    try:
        result = push_products(
            retailer=options.get('retailer'),
            dry_run=bool(options.get('dry_run', False)),
            limit=options.get('limit'),
            with_stock=bool(options.get('with_stock', True)),
            update_existing=bool(options.get('update_existing', True)),
            branch_filter=options.get('branch_filter'),
            product_type=options.get('product_type', 'storable'),
            progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('Odoo push job %s failed', job_id)
        KvSyncJob.objects.filter(pk=job_id).update(
            status=KvSyncJob.STATUS_FAILED,
            finished_at=timezone.now(),
            progress_percent=100,
            message=f'Lỗi: {str(exc)[:500]}',
        )
        return

    s = result.summary()
    parts = [
        f'Tạo {s["products_created"]} SP',
        f'cập nhật {s["products_updated"]}',
        f'{s["categories_created"]} danh mục',
        f'{s["warehouses_created"]} kho',
        f'{s["stock_applied"]} dòng tồn',
    ]
    if s['products_failed'] or s['stock_failed']:
        parts.append(f'lỗi SP {s["products_failed"]}, lỗi tồn {s["stock_failed"]}')
    prefix = '[DRY-RUN] ' if s['dry_run'] else ''

    job.refresh_from_db()
    job.status = KvSyncJob.STATUS_SUCCESS
    job.progress_percent = 100
    job.finished_at = timezone.now()
    job.rows_synced = s['products_created'] + s['products_updated']
    job.current_entity = ''
    job.entity_results = [s]
    job.message = prefix + ' · '.join(parts)
    job.save()


def start_odoo_push_async(*, user, options: dict) -> KvSyncJob:
    if KvSyncJob.objects.filter(
        status__in=(KvSyncJob.STATUS_PENDING, KvSyncJob.STATUS_RUNNING),
    ).exists():
        raise OdooPushRunnerError('Đang có job khác chạy — vui lòng đợi hoàn tất.')

    job = KvSyncJob.objects.create(
        trigger=KvSyncJob.TRIGGER_MANUAL,
        status=KvSyncJob.STATUS_PENDING,
        full_sync=False,
        entities=[ODOO_PUSH_MARKER],
        started_by=user,
    )

    def _worker():
        try:
            run_odoo_push_job(job_id=job.pk, options=options)
        except Exception as exc:  # noqa: BLE001
            logger.exception('Odoo push job %s crashed', job.pk)
            KvSyncJob.objects.filter(pk=job.pk).update(
                status=KvSyncJob.STATUS_FAILED,
                finished_at=timezone.now(),
                message=str(exc)[:2000],
                progress_percent=100,
            )
        finally:
            connection.close()

    threading.Thread(target=_worker, daemon=True).start()
    return job
