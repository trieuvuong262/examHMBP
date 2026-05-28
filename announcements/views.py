from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from assessment.decorators import admin_only

from .forms import AnnouncementForm
from .models import Announcement, AnnouncementRead


def _active_announcements():
    return Announcement.objects.filter(is_active=True)


@login_required
def announcement_list(request):
    announcements = _active_announcements()
    read_ids = set(
        AnnouncementRead.objects.filter(
            user=request.user,
            announcement__in=announcements,
        ).values_list('announcement_id', flat=True)
    )

    items = [{'object': item, 'is_read': item.id in read_ids} for item in announcements]

    context = {
        'items': items,
        'is_admin': request.user.is_staff,
        'unread_count': sum(1 for x in items if not x['is_read']),
    }
    return render(request, 'announcements/list.html', context)


@login_required
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
        'is_admin': request.user.is_staff,
    }
    return render(request, 'announcements/detail.html', context)


@admin_only
def admin_list(request):
    announcements = Announcement.objects.annotate(
        read_count=Count('reads'),
    ).order_by('-is_pinned', '-created_at')

    return render(request, 'announcements/admin/list.html', {
        'announcements': announcements,
    })


@admin_only
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


@admin_only
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


@admin_only
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
