from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from hrm.module_permissions import MODULE_AUDIT, MODULE_LABELS, user_can_access_module
from hrm.permissions import ROLE_CHOICES

from .models import UserActivityLog


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


@_audit_access_required
def log_list(request):
    qs = UserActivityLog.objects.select_related('user').all()

    user_id = request.GET.get('user', '').strip()
    action = request.GET.get('action', '').strip()
    module_key = request.GET.get('module', '').strip()
    method = request.GET.get('method', '').strip()
    ip = request.GET.get('ip', '').strip()
    q = request.GET.get('q', '').strip()
    date_from = request.GET.get('from', '').strip()
    date_to = request.GET.get('to', '').strip()
    status = request.GET.get('status', '').strip()

    if user_id.isdigit():
        qs = qs.filter(user_id=int(user_id))
    if action:
        qs = qs.filter(action=action)
    if module_key:
        qs = qs.filter(module_key=module_key)
    if method:
        qs = qs.filter(method__iexact=method)
    if ip:
        qs = qs.filter(ip_address__icontains=ip)
    if status.isdigit():
        qs = qs.filter(status_code=int(status))
    if q:
        qs = qs.filter(
            Q(summary__icontains=q)
            | Q(path__icontains=q)
            | Q(username__icontains=q)
            | Q(full_name__icontains=q)
            | Q(object_repr__icontains=q)
            | Q(url_name__icontains=q)
        )
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

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
        'failed_logins_today': UserActivityLog.objects.filter(
            action=UserActivityLog.ACTION_LOGIN_FAILED,
            created_at__date=timezone.localdate(),
        ).count(),
    }

    return render(request, 'audit/log_list.html', {
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'users_with_logs': users_with_logs,
        'action_choices': UserActivityLog.ACTION_CHOICES,
        'module_choices': MODULE_LABELS.items(),
        'role_choices': ROLE_CHOICES,
        'filters': {
            'user': user_id,
            'action': action,
            'module': module_key,
            'method': method,
            'ip': ip,
            'q': q,
            'from': date_from,
            'to': date_to,
            'status': status,
        },
        'stats': stats,
    })


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

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'audit/user_timeline.html', {
        'target_user': target_user,
        'page_obj': page_obj,
        'logs': page_obj.object_list,
    })
