from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from PortalJustPlay.list_search import apply_combined_search, apply_term_search, apply_user_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from assessment.decorators import module_perm_required

from hrm.module_permissions import (
    MODULE_ANNOUNCEMENTS,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_update_module,
)

from .forms import AnnouncementForm
from .models import Announcement, AnnouncementRead


def _active_announcements():
    return Announcement.objects.filter(is_active=True)


def _announcement_perm_context(user):
    return {
        'is_admin': user_can_edit_module(user, MODULE_ANNOUNCEMENTS),
        'can_create': user_can_create_module(user, MODULE_ANNOUNCEMENTS),
        'can_update': user_can_update_module(user, MODULE_ANNOUNCEMENTS),
        'can_delete': user_can_delete_module(user, MODULE_ANNOUNCEMENTS),
    }


@module_perm_required(MODULE_ANNOUNCEMENTS, 'view')
def announcement_list(request):
    search_query = get_search_query(request)
    announcements_qs = _active_announcements().order_by('-is_pinned', '-created_at')
    announcements_qs = apply_term_search(
        announcements_qs, search_query,
        'title__icontains', 'summary__icontains',
    )
    page_obj, query_string = paginate_queryset(request, announcements_qs)
    announcements = page_obj.object_list

    read_ids = set(
        AnnouncementRead.objects.filter(
            user=request.user,
            announcement__in=announcements,
        ).values_list('announcement_id', flat=True)
    )

    items = [{'object': item, 'is_read': item.id in read_ids} for item in announcements]

    context = {
        'items': items,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'unread_count': sum(1 for x in items if not x['is_read']),
        **_announcement_perm_context(request.user),
    }
    return render(request, 'announcements/list.html', context)


@module_perm_required(MODULE_ANNOUNCEMENTS, 'view')
def announcement_detail(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk, is_active=True)
    is_read = AnnouncementRead.objects.filter(
        announcement=announcement,
        user=request.user,
    ).exists()

    if request.method == 'POST' and request.POST.get('action') == 'acknowledge':
        AnnouncementRead.objects.get_or_create(
            announcement=announcement,
            user=request.user,
        )
        messages.success(request, 'Đã xác nhận đọc thông báo.')
        return redirect('announcements:detail', pk=pk)

    context = {
        'announcement': announcement,
        'is_read': is_read,
        **_announcement_perm_context(request.user),
    }
    return render(request, 'announcements/detail.html', context)


@module_perm_required(MODULE_ANNOUNCEMENTS, 'edit')
def admin_list(request):
    search_query = get_search_query(request)
    announcements_qs = Announcement.objects.annotate(
        read_count=Count('reads'),
    ).order_by('-is_pinned', '-created_at')
    announcements_qs = apply_term_search(
        announcements_qs, search_query,
        'title__icontains', 'summary__icontains',
    )
    page_obj, query_string = paginate_queryset(request, announcements_qs)

    return render(request, 'announcements/admin/list.html', {
        'announcements': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        **_announcement_perm_context(request.user),
    })


@module_perm_required(MODULE_ANNOUNCEMENTS, 'create')
def admin_create(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, request.FILES)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.created_by = request.user
            announcement.save()
            messages.success(request, 'Đã tạo thông báo mới.')
            return redirect('announcements:admin_list')
    else:
        form = AnnouncementForm()

    return render(request, 'announcements/admin/form.html', {
        'form': form,
        'title': 'Tạo thông báo mới',
    })


@module_perm_required(MODULE_ANNOUNCEMENTS, 'update')
def admin_edit(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)

    if request.method == 'POST':
        form = AnnouncementForm(request.POST, request.FILES, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật thông báo.')
            return redirect('announcements:admin_list')
    else:
        form = AnnouncementForm(instance=announcement)

    return render(request, 'announcements/admin/form.html', {
        'form': form,
        'title': 'Chỉnh sửa thông báo',
        'announcement': announcement,
    })


@module_perm_required(MODULE_ANNOUNCEMENTS, 'delete')
def admin_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)

    if request.method == 'POST':
        title = announcement.title
        announcement.delete()
        messages.success(request, f'Đã xóa thông báo "{title}".')
        return redirect('announcements:admin_list')

    return render(request, 'announcements/admin/confirm_delete.html', {
        'announcement': announcement,
    })
