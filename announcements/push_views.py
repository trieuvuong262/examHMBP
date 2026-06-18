"""API poll thông báo mới — hiện notification khi user đang mở portal."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_ANNOUNCEMENTS
from utilities.portal_push_eligibility import user_portal_push_debug
from utilities.push_service import webpush_configured

from .models import Announcement, AnnouncementRead


def _json_error(message: str, *, status: int = 400):
    return JsonResponse({'ok': False, 'message': message}, status=status)


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


@login_required
@require_http_methods(['POST'])
@module_perm_required(MODULE_ANNOUNCEMENTS, 'view')
def push_test(request):
    if not webpush_configured():
        return _json_error('Web push chưa được cấu hình trên server.', status=503)
    if not user_portal_push_debug(request.user):
        return _json_error('Chỉ admin được gửi thử.', status=403)

    from announcements.push_service import send_test_announcement_push

    stats = send_test_announcement_push(request.user)
    if stats.get('reason') == 'no_subscription':
        return _json_error('Chưa đăng ký push trên thiết bị này.')
    if stats.get('sent', 0) < 1:
        return _json_error('Không gửi được thông báo thử. Thử bật lại đăng ký push.')
    return JsonResponse({
        'ok': True,
        'message': 'Đã gửi thông báo thử — kiểm tra góc màn hình.',
        'sent': stats['sent'],
    })
