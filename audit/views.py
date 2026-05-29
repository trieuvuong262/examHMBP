from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from PortalJustPlay.list_search import apply_combined_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from hrm.module_permissions import MODULE_AUDIT, user_can_access_module

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
