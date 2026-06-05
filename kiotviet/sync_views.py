"""Trang quản trị đồng bộ KiotViet (menu Quản Trị Hệ thống)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from hrm.module_permissions import MODULE_AUDIT, user_can_access_module, user_can_edit_module

from .client import KiotVietClient
from .mirror import mirror_summary, sync_states
from .models import KvSyncConfig, KvSyncJob
from .sync_helpers import SYNC_INTERVAL_CHOICES, cron_hint_for_minutes, normalize_interval_minutes
from .sync_runner import KvSyncRunnerError, active_sync_job, latest_sync_job, start_sync_async
from .sync_service import ENTITY_ALL, ENTITY_LABELS, current_retailer


def _audit_access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_AUDIT):
            messages.error(request, 'Bạn không có quyền truy cập Quản Trị Hệ thống.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _parse_entities(post) -> list[str]:
    selected = post.getlist('entities')
    return [e for e in selected if e in ENTITY_ALL]


def _sync_page_context(user) -> dict:
    retailer = current_retailer()
    configured = KiotVietClient.is_configured()
    config = KvSyncConfig.get_for_retailer(retailer) if retailer else None
    state_by_entity = {s.entity_type: s for s in sync_states(retailer)}
    entity_rows = []
    for entity in ENTITY_ALL:
        state = state_by_entity.get(entity)
        entity_rows.append({
            'key': entity,
            'label': ENTITY_LABELS.get(entity, entity),
            'enabled': entity in (config.enabled_entities if config else ENTITY_ALL),
            'records': state.records_total if state else 0,
            'last_success_at': state.last_success_at if state else None,
            'last_error': (state.last_error or '') if state else '',
        })

    active_job = active_sync_job()
    latest_job = latest_sync_job()
    running_job = active_job or (
        latest_job if latest_job and latest_job.is_active else None
    )
    interval_minutes = config.interval_minutes if config else 30

    return {
        'can_edit': user_can_edit_module(user, MODULE_AUDIT),
        'configured': configured,
        'retailer': retailer,
        'config': config,
        'interval_choices': SYNC_INTERVAL_CHOICES,
        'entity_rows': entity_rows,
        'entity_labels': ENTITY_LABELS,
        'mirror_counts': mirror_summary(retailer) if retailer else {},
        'active_job': running_job,
        'latest_job': latest_job,
        'cron_hint': cron_hint_for_minutes(interval_minutes),
    }


@_audit_access_required
def kiotviet_sync_page(request):
    ctx = _sync_page_context(request.user)
    poll_job_id = request.GET.get('job', '').strip()
    if poll_job_id.isdigit():
        ctx['poll_job_id'] = int(poll_job_id)
    elif ctx.get('active_job'):
        ctx['poll_job_id'] = ctx['active_job'].pk
    return render(request, 'audit/kiotviet_sync.html', ctx)


@_audit_access_required
@require_POST
def kiotviet_sync_save(request):
    if not user_can_edit_module(request.user, MODULE_AUDIT):
        messages.error(request, 'Bạn không có quyền lưu cấu hình đồng bộ.')
        return redirect('audit:kiotviet_sync')

    retailer = current_retailer()
    if not retailer:
        messages.error(request, 'KIOTVIET_RETAILER chưa cấu hình trong .env.')
        return redirect('audit:kiotviet_sync')

    entities = _parse_entities(request.POST)
    if not entities:
        messages.error(request, 'Chọn ít nhất một mục cần đồng bộ.')
        return redirect('audit:kiotviet_sync')

    config = KvSyncConfig.get_for_retailer(retailer)
    config.interval_minutes = normalize_interval_minutes(request.POST.get('interval_minutes'))
    config.schedule_enabled = request.POST.get('schedule_enabled') == 'on'
    config.enabled_entities = entities
    config.updated_by = request.user
    config.save()

    messages.success(request, 'Đã lưu cấu hình đồng bộ KiotViet (chỉ sync mới/thay đổi).')
    return redirect('audit:kiotviet_sync')


@_audit_access_required
@require_POST
def kiotviet_sync_run(request):
    if not user_can_edit_module(request.user, MODULE_AUDIT):
        messages.error(request, 'Bạn không có quyền chạy đồng bộ thủ công.')
        return redirect('audit:kiotviet_sync')

    if not KiotVietClient.is_configured():
        messages.error(request, 'KiotViet chưa cấu hình. Kiểm tra biến môi trường KIOTVIET_*.')
        return redirect('audit:kiotviet_sync')

    entities = _parse_entities(request.POST)
    if not entities:
        retailer = current_retailer()
        if retailer:
            config = KvSyncConfig.get_for_retailer(retailer)
            entities = list(config.enabled_entities or ENTITY_ALL)
    if not entities:
        messages.error(request, 'Chọn ít nhất một mục cần đồng bộ.')
        return redirect('audit:kiotviet_sync')

    full_sync = request.POST.get('full_sync') == 'on'
    try:
        job = start_sync_async(
            trigger=KvSyncJob.TRIGGER_MANUAL,
            user=request.user,
            entities=entities,
            full_sync=full_sync,
        )
    except KvSyncRunnerError as exc:
        messages.error(request, str(exc))
        return redirect('audit:kiotviet_sync')

    return redirect(reverse('audit:kiotviet_sync') + f'?job={job.pk}')


@_audit_access_required
@require_GET
def kiotviet_sync_status(request, job_id: int):
    try:
        job = KvSyncJob.objects.get(pk=job_id)
    except KvSyncJob.DoesNotExist:
        return JsonResponse({'error': 'Job không tồn tại.'}, status=404)

    entities = list(job.entities or [])
    entity_total = len(entities)
    entity_label = ENTITY_LABELS.get(job.current_entity, job.current_entity)
    entity_index = 0
    if job.current_entity and job.current_entity in entities:
        entity_index = entities.index(job.current_entity) + 1
    elif not job.is_active and entity_total:
        entity_index = entity_total

    return JsonResponse({
        'id': job.pk,
        'status': job.status,
        'status_display': job.get_status_display(),
        'progress_percent': job.progress_percent,
        'current_entity': job.current_entity,
        'current_entity_label': entity_label,
        'entity_index': entity_index,
        'entity_total': entity_total,
        'message': job.message,
        'rows_synced': job.rows_synced,
        'is_active': job.is_active,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'duration_display': job.duration_display,
        'entity_results': job.entity_results,
    })
