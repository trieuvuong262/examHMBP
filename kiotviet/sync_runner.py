"""Chạy job đồng bộ KiotViet nền (thread) với cập nhật tiến độ."""

from __future__ import annotations

import logging
import threading

from django.db import connection
from django.utils import timezone

from .client import KiotVietClient
from .models import KvSyncJob
from .sync_service import ENTITY_LABELS, sync_entity

logger = logging.getLogger(__name__)


class KvSyncRunnerError(Exception):
    pass


def _calc_progress(entity_idx: int, entity_total: int, current_item: int, api_total: int) -> int:
    if entity_total <= 0:
        return 1
    entity_weight = 100.0 / entity_total
    base = entity_idx * entity_weight
    if api_total > 0:
        pct = base + min(1.0, current_item / api_total) * entity_weight
    else:
        pct = base + entity_weight * 0.4
    return max(1, min(99, int(pct)))


def _entity_milestone(entity_idx: int, entity_total: int) -> int:
    if entity_total <= 0:
        return 99
    return max(1, min(99, int((entity_idx + 1) / entity_total * 100)))


def run_sync_job(*, job_id: int) -> None:
    job = KvSyncJob.objects.get(pk=job_id)
    if job.status not in (KvSyncJob.STATUS_PENDING, KvSyncJob.STATUS_RUNNING):
        return

    job.status = KvSyncJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.progress_percent = 1
    job.message = 'Đang khởi động đồng bộ…'
    job.save(update_fields=['status', 'started_at', 'progress_percent', 'message'])

    entities = [e for e in (job.entities or []) if e]
    if not entities:
        job.status = KvSyncJob.STATUS_FAILED
        job.finished_at = timezone.now()
        job.message = 'Không có mục nào được chọn để đồng bộ.'
        job.save(update_fields=['status', 'finished_at', 'message'])
        return

    if not KiotVietClient.is_configured():
        job.status = KvSyncJob.STATUS_FAILED
        job.finished_at = timezone.now()
        job.message = 'KiotViet chưa cấu hình (KIOTVIET_ENABLED / credentials).'
        job.save(update_fields=['status', 'finished_at', 'message'])
        return

    client = KiotVietClient()
    results: list[dict] = []
    rows_total = 0
    has_error = False
    entity_total = len(entities)

    for entity_idx, entity in enumerate(entities):
        label = ENTITY_LABELS.get(entity, entity)

        def on_progress(current_item: int, api_total: int, entity_type: str) -> None:
            KvSyncJob.objects.filter(pk=job_id).update(
                progress_percent=_calc_progress(entity_idx, entity_total, current_item, api_total),
                current_entity=entity_type,
                message=f'Đang đồng bộ {label}…',
            )

        KvSyncJob.objects.filter(pk=job_id).update(
            progress_percent=_calc_progress(entity_idx, entity_total, 0, 0),
            current_entity=entity,
            message=f'Đang đồng bộ {label}…',
        )

        try:
            result = sync_entity(
                entity,
                full=job.full_sync,
                client=client,
                on_progress=on_progress,
            )
        except Exception as exc:
            logger.exception('KiotViet sync job %s entity %s failed', job_id, entity)
            result = {'entity': entity, 'error': str(exc)}
            has_error = True

        results.append(result)
        if result.get('error'):
            has_error = True
        else:
            rows_total += int(result.get('upserted') if result.get('upserted') is not None else result.get('rows') or 0)

        KvSyncJob.objects.filter(pk=job_id).update(
            entity_results=results,
            rows_synced=rows_total,
            progress_percent=_entity_milestone(entity_idx, entity_total),
            message=f'Hoàn tất {label} ({entity_idx + 1}/{entity_total})',
        )

    job.refresh_from_db()
    job.entity_results = results
    job.rows_synced = rows_total
    job.progress_percent = 100
    job.finished_at = timezone.now()
    skipped_total = sum(int(r.get('skipped') or 0) for r in results if not r.get('error'))
    if has_error:
        failed = [r.get('entity') for r in results if r.get('error')]
        job.status = KvSyncJob.STATUS_FAILED
        job.message = f'Hoàn tất với lỗi: {", ".join(failed)}'
    else:
        job.status = KvSyncJob.STATUS_SUCCESS
        if skipped_total:
            job.message = (
                f'Cập nhật {rows_total:,} bản ghi mới/thay đổi · '
                f'bỏ qua {skipped_total:,} bản ghi không đổi.'
            )
        else:
            job.message = f'Cập nhật {rows_total:,} bản ghi mới/thay đổi.'
    job.current_entity = ''
    job.save()


def start_sync_async(
    *,
    trigger: str,
    user,
    entities: list[str],
    full_sync: bool = False,
) -> KvSyncJob:
    if KvSyncJob.objects.filter(
        status__in=(KvSyncJob.STATUS_PENDING, KvSyncJob.STATUS_RUNNING),
    ).exists():
        raise KvSyncRunnerError('Đang có job đồng bộ khác — vui lòng đợi hoàn tất.')

    job = KvSyncJob.objects.create(
        trigger=trigger,
        status=KvSyncJob.STATUS_PENDING,
        full_sync=full_sync,
        entities=list(entities),
        started_by=user,
    )

    def _worker():
        try:
            run_sync_job(job_id=job.pk)
        except Exception as exc:
            logger.exception('KiotViet sync job %s crashed', job.pk)
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


def latest_sync_job() -> KvSyncJob | None:
    return KvSyncJob.objects.order_by('-created_at').first()


def active_sync_job() -> KvSyncJob | None:
    return (
        KvSyncJob.objects.filter(status__in=(KvSyncJob.STATUS_PENDING, KvSyncJob.STATUS_RUNNING))
        .order_by('-created_at')
        .first()
    )
