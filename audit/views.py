from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from PortalJustPlay.list_search import apply_combined_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from hrm.module_permissions import MODULE_AUDIT, MODULE_HRM, user_can_access_module, user_can_edit_module
from hrm.user_search import exclude_hidden_hrm_users, filter_users_by_search

from .models import PortalBackupJob, UserActivityLog
from .portal_backup import PortalBackupError, latest_backup_job, start_backup_async


def _audit_access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_AUDIT):
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, 'Bạn không có quyền xem nhật ký thao tác.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _backup_page_context(user):
    backup_job = latest_backup_job()
    backup_running = PortalBackupJob.objects.filter(
        status__in=(PortalBackupJob.STATUS_PENDING, PortalBackupJob.STATUS_RUNNING),
    ).exists()
    return {
        'can_run_backup': user_can_edit_module(user, MODULE_AUDIT),
        'backup_job': backup_job,
        'backup_running': backup_running,
    }


@_audit_access_required
def backup_page(request):
    return render(request, 'audit/backup.html', _backup_page_context(request.user))


@_audit_access_required
def nas_links_index(request):
    if not user_can_edit_module(request.user, MODULE_HRM):
        messages.error(request, 'Bạn không có quyền cập nhật link NAS.')
        return redirect('home_portal')

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


@_audit_access_required
def log_list(request):
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

    filters = {
        'user': user_id,
        'q': q,
        'from': date_from,
        'to': date_to,
    }

    return render(request, 'audit/log_list.html', {
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'users_with_logs': users_with_logs,
        'filters': filters,
        'filter_query': filter_query,
        'stats': stats,
    })


@_audit_access_required
@require_POST
def backup_run(request):
    if not user_can_edit_module(request.user, MODULE_AUDIT):
        messages.error(request, 'Chỉ tài khoản có quyền sửa Nhật ký mới được chạy backup.')
        return redirect('audit:backup_page')
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


@_audit_access_required
def log_detail(request, pk):
    log = get_object_or_404(UserActivityLog.objects.select_related('user'), pk=pk)
    return render(request, 'audit/log_detail.html', {
        'log': log,
    })


@_audit_access_required
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
