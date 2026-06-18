"""API poll thông báo mới — hiện notification khi user đang mở portal."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_ANNOUNCEMENTS

from .models import Announcement, AnnouncementRead


@require_GET
@login_required
@module_perm_required(MODULE_ANNOUNCEMENTS, 'view')
def poll_unread(request):
    read_ids = set(
        AnnouncementRead.objects.filter(user=request.user).values_list('announcement_id', flat=True),
    )
    announcement = (
        Announcement.objects.filter(is_active=True)
        .exclude(pk__in=read_ids)
        .order_by('-created_at', '-pk')
        .first()
    )
    if not announcement:
        return JsonResponse({'ok': True, 'has_new': False})

    return JsonResponse({
        'ok': True,
        'has_new': True,
        'announcement_id': announcement.pk,
        'title': announcement.title,
        'summary': (announcement.summary or '')[:240],
        'url': reverse('announcements:detail', kwargs={'pk': announcement.pk}),
    })
