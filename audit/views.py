import io
from datetime import datetime

import pandas as pd
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from PortalJustPlay.list_search import apply_combined_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from assessment.decorators import module_perm_required
from hrm.module_permissions import (
    MODULE_AUDIT,
    MODULE_HRM,
    user_can_export_module,
    user_can_update_module,
)

from .models import PortalBackupJob, UserActivityLog
from .portal_backup import PortalBackupError, latest_backup_job, start_backup_async


def _activity_log_queryset_from_request(request):
    qs = UserActivityLog.objects.select_related('user').all()

    user_id = request.GET.get('user', '').strip()
    q = get_search_query(request)
    date_from = request.GET.get('from', '').strip()
    date_to = request.GET.get('to', '').strip()

    if user_id.isdigit():
        qs = qs.filter(user_id=int(user_id))
    qs = apply_combined_search(qs, q, lambda term: (
        Q(summary__icontains=term)
        | Q(username__icontains=term)
        | Q(full_name__icontains=term)
        | Q(machine_name__icontains=term)
        | Q(ip_address__icontains=term)
    ))
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs, {
        'user': user_id,
        'q': q,
        'from': date_from,
        'to': date_to,
    }


def _backup_page_context(user):
    backup_job = latest_backup_job()
    backup_running = PortalBackupJob.objects.filter(
        status__in=(PortalBackupJob.STATUS_PENDING, PortalBackupJob.STATUS_RUNNING),
    ).exists()
    return {
        'can_run_backup': user_can_export_module(user, MODULE_AUDIT),
        'backup_job': backup_job,
        'backup_running': backup_running,
    }


@module_perm_required(MODULE_AUDIT, 'view')
def backup_page(request):
    return render(request, 'audit/backup.html', _backup_page_context(request.user))


@module_perm_required(MODULE_AUDIT, 'view')
def nas_links_index(request):
    if not user_can_update_module(request.user, MODULE_HRM):
        messages.error(request, 'Bạn không có quyền cập nhật link NAS.')
        return redirect('home_portal')

    from hrm.user_search import exclude_hidden_hrm_users, filter_users_by_search
    from nas_storage.user_folders import nas_folders_feature_available

    search_query = get_search_query(request)
    users_qs = User.objects.select_related('profile', 'profile__department')
    users_qs = exclude_hidden_hrm_users(users_qs)
    users_qs = filter_users_by_search(users_qs, search_query)
    users_qs = users_qs.order_by('profile__full_name', 'username')
    page_obj, query_string = paginate_queryset(request, users_qs)

    return render(request, 'audit/nas_links.html', {
        'users': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'nas_folders_available': nas_folders_feature_available(),
    })


@module_perm_required(MODULE_AUDIT, 'view')
def log_list(request):
    qs, filters = _activity_log_queryset_from_request(request)
    page_obj, filter_query = paginate_queryset(request, qs)

    users_with_logs = (
        User.objects.filter(activity_logs__isnull=False)
        .distinct()
        .order_by('username')
    )

    stats = {
        'total': UserActivityLog.objects.count(),
        'today': UserActivityLog.objects.filter(
            created_at__date=timezone.localdate(),
        ).count(),
    }

    return render(request, 'audit/log_list.html', {
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'users_with_logs': users_with_logs,
        'filters': filters,
        'filter_query': filter_query,
        'stats': stats,
        'can_export': user_can_export_module(request.user, MODULE_AUDIT),
    })


@module_perm_required(MODULE_AUDIT, 'export')
def log_export_excel(request):
    qs, _filters = _activity_log_queryset_from_request(request)
    rows = []
    for log in qs.order_by('-created_at')[:50000]:
        rows.append({
            'Thời gian': timezone.localtime(log.created_at).strftime('%d/%m/%Y %H:%M:%S'),
            'Tài khoản': log.username,
            'Họ tên': log.full_name,
            'Hành động': log.get_action_display(),
            'Mô tả': log.summary,
            'Module': log.module_label or log.module_key,
            'Tên máy': log.machine_name,
            'IP': log.ip_address,
            'Đường dẫn': log.path,
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Nhat_ky')

    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename=Nhat_ky_thao_tac_{stamp}.xlsx'
    return response


@module_perm_required(MODULE_AUDIT, 'export')
@require_POST
def backup_run(request):
    try:
        job = start_backup_async(trigger=PortalBackupJob.TRIGGER_MANUAL, user=request.user)
    except PortalBackupError as exc:
        messages.error(request, str(exc))
        return redirect('audit:backup_page')
    messages.success(
        request,
        f'Đã bắt đầu backup lên NAS (job #{job.pk}). Tải lại trang sau vài phút để xem kết quả.',
    )
    return redirect('audit:backup_page')


@module_perm_required(MODULE_AUDIT, 'view')
def log_detail(request, pk):
    log = get_object_or_404(UserActivityLog.objects.select_related('user'), pk=pk)
    return render(request, 'audit/log_detail.html', {
        'log': log,
    })


@module_perm_required(MODULE_AUDIT, 'view')
def user_timeline(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    qs = UserActivityLog.objects.filter(
        Q(user=target_user) | Q(username=target_user.username),
    ).select_related('user')
    search_query = get_search_query(request)
    qs = apply_combined_search(qs, search_query, lambda term: (
        Q(summary__icontains=term)
        | Q(machine_name__icontains=term)
        | Q(ip_address__icontains=term)
    ))

    page_obj, query_string = paginate_queryset(request, qs)

    return render(request, 'audit/user_timeline.html', {
        'target_user': target_user,
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'query_string': query_string,
        'search_query': search_query,
    })
