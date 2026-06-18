"""API đăng ký / huỷ web push portal (đặt cơm + thông báo)."""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from utilities.models import MealPushSubscription
from utilities.portal_push_eligibility import user_portal_push_debug, user_portal_push_eligible
from utilities.push_service import webpush_configured


def _json_error(message: str, *, status: int = 400):
    return JsonResponse({'ok': False, 'message': message}, status=status)


@require_GET
@login_required
def vapid_public_key(request):
    if not webpush_configured():
        return _json_error('Web push chưa được cấu hình trên server.', status=503)
    if not user_portal_push_eligible(request.user):
        return _json_error('Tài khoản không đủ điều kiện nhận thông báo đẩy.', status=403)
    from django.conf import settings

    return JsonResponse({
        'ok': True,
        'publicKey': settings.WEBPUSH_VAPID_PUBLIC_KEY,
    })


@login_required
@require_http_methods(['POST'])
def push_subscribe(request):
    if not webpush_configured():
        return _json_error('Web push chưa được cấu hình trên server.', status=503)
    if not user_portal_push_eligible(request.user):
        return _json_error('Tài khoản không đủ điều kiện nhận thông báo đẩy.', status=403)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return _json_error('Dữ liệu đăng ký không hợp lệ.')

    endpoint = (body.get('endpoint') or '').strip()
    keys = body.get('keys') or {}
    p256dh = (keys.get('p256dh') or '').strip()
    auth = (keys.get('auth') or '').strip()
    if not endpoint or not p256dh or not auth:
        return _json_error('Thiếu endpoint hoặc khoá push.')

    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:300]
    subscription, created = MealPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user': request.user,
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': user_agent,
        },
    )
    return JsonResponse({
        'ok': True,
        'created': created,
        'id': subscription.pk,
    })


@login_required
@require_http_methods(['POST'])
def push_unsubscribe(request):
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}

    endpoint = (body.get('endpoint') or '').strip()
    qs = MealPushSubscription.objects.filter(user=request.user)
    if endpoint:
        qs = qs.filter(endpoint=endpoint)
    deleted, _ = qs.delete()
    return JsonResponse({'ok': True, 'deleted': deleted})


@require_GET
@login_required
def push_status(request):
    if not webpush_configured():
        return _json_error('Web push chưa được cấu hình trên server.', status=503)
    if not user_portal_push_eligible(request.user):
        return _json_error('Tài khoản không đủ điều kiện nhận thông báo đẩy.', status=403)

    count = MealPushSubscription.objects.filter(user=request.user).count()
    return JsonResponse({
        'ok': True,
        'subscribed': count > 0,
        'subscription_count': count,
    })


@login_required
@require_http_methods(['POST'])
def push_test(request):
    if not webpush_configured():
        return _json_error('Web push chưa được cấu hình trên server.', status=503)
    if not user_portal_push_debug(request.user):
        return _json_error('Chỉ admin được gửi thử.', status=403)
    if not user_portal_push_eligible(request.user):
        return _json_error('Tài khoản không đủ điều kiện nhận thông báo đẩy.', status=403)

    from utilities.push_service import send_test_meal_push

    stats = send_test_meal_push(request.user)
    if stats.get('reason') == 'no_subscription':
        return _json_error('Chưa đăng ký nhắc đẩy trên thiết bị này.')
    if stats.get('sent', 0) < 1:
        remaining = MealPushSubscription.objects.filter(user=request.user).count()
        if remaining == 0 and stats.get('failed', 0) > 0:
            return _json_error('Đăng ký cũ đã hết hạn. Bấm «Cho phép nhận nhắc» lại trên trình duyệt này.')
        return _json_error('Không gửi được thông báo thử. Thử bật lại nhắc đẩy.')
    return JsonResponse({
        'ok': True,
        'message': 'Đã gửi thông báo thử — kiểm tra góc màn hình.',
        'sent': stats['sent'],
    })
