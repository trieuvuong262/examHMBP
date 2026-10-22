from django.db.utils import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.shortcuts import redirect


class AttendancePunchGateMiddleware:
    """Trong khung nhắc ca, chưa chấm vào thì mọi trang khác quay về màn chấm công."""

    _ALLOW_PREFIXES = (
        '/accounts/logout',
        '/accounts/login',
        '/change-password',
        '/static/',
        '/media/',
        '/admin-panel/',
    )
    _ALLOW_EXACT = frozenset({
        '/sw.js',
        '/manifest.webmanifest',
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return self.get_response(request)
        path = request.path or '/'
        if path.rstrip('/') == '/cham-cong' or path in self._ALLOW_EXACT or any(
            path.startswith(prefix) for prefix in self._ALLOW_PREFIXES
        ):
            return self.get_response(request)
        try:
            from cham_cong.services import should_force_punch
            blocked = should_force_punch(user)
        except (OperationalError, ProgrammingError):
            blocked = False
        if not blocked:
            return self.get_response(request)
        accept = request.headers.get('Accept', '')
        if (
            'application/json' in accept
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        ):
            return JsonResponse(
                {'status': 'error', 'message': 'Cần chấm công vào trước khi tiếp tục.'},
                status=409,
            )
        return redirect('cham_cong:punch')
