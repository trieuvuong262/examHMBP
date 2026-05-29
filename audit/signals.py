from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from audit.models import UserActivityLog
from audit.utils import create_activity_log, get_client_device_info


class _SignalRequestProxy:
    """Proxy tối giản cho signal không có HttpRequest đầy đủ."""

    def __init__(self, request):
        self._request = request

    def __getattr__(self, item):
        return getattr(self._request, item)


@receiver(user_logged_in)
def audit_user_logged_in(sender, request, user, **kwargs):
    create_activity_log(
        request=request,
        user=user,
        action=UserActivityLog.ACTION_LOGIN,
        summary=f'{user.get_full_name() or user.username} đăng nhập thành công vào portal',
        path=request.path,
        method='POST',
        status_code=302,
        extra={'backend': kwargs.get('backend', '')},
    )


@receiver(user_logged_out)
def audit_user_logged_out(sender, request, user, **kwargs):
    if user is None:
        return
    create_activity_log(
        request=request,
        user=user,
        action=UserActivityLog.ACTION_LOGOUT,
        summary=f'{user.get_full_name() or user.username} bấm Đăng xuất khỏi hệ thống',
        path=request.path,
        method='POST',
        status_code=302,
    )


@receiver(user_login_failed)
def audit_user_login_failed(sender, credentials, request, **kwargs):
    if request is None:
        return
    username = credentials.get('username', '')
    create_activity_log(
        request=request,
        user=None,
        username_override=username,
        action=UserActivityLog.ACTION_LOGIN_FAILED,
        summary=f'Đăng nhập thất bại — thử tài khoản [{username or "Không rõ"}]',
        path=request.path,
        method='POST',
        status_code=401,
        request_data={'body': {'username': username}},
        extra={'device': get_client_device_info(request)},
    )
