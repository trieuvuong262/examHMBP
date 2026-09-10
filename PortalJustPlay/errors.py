"""Trang lỗi HTTP thân thiện (404 / 403 / 500)."""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import loader
from django.views.decorators.csrf import requires_csrf_token


def _wants_json(request) -> bool:
    accept = request.headers.get('Accept') or ''
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in accept
    )


def _error_context(*, title: str, extra: dict | None = None) -> dict:
    ctx = {'jp_page_title': title}
    if extra:
        ctx.update(extra)
    return ctx


def page_not_found(request, exception):
    if _wants_json(request):
        return JsonResponse(
            {'status': 'error', 'code': 404, 'message': 'Không tìm thấy trang.'},
            status=404,
        )
    return render(
        request,
        '404.html',
        _error_context(
            title='Không tìm thấy trang',
            extra={'request_path': request.get_full_path()},
        ),
        status=404,
    )


def permission_denied(request, exception):
    if _wants_json(request):
        return JsonResponse(
            {'status': 'error', 'code': 403, 'message': 'Không có quyền truy cập.'},
            status=403,
        )
    return render(
        request,
        '403.html',
        _error_context(
            title='Không có quyền truy cập',
            extra={'request_path': request.get_full_path()},
        ),
        status=403,
    )


@requires_csrf_token
def server_error(request):
    """500 không dùng RequestContext — tránh context processor làm hỏng thêm."""
    if _wants_json(request):
        return JsonResponse(
            {'status': 'error', 'code': 500, 'message': 'Hệ thống đang gặp sự cố.'},
            status=500,
        )
    template = loader.get_template('500.html')
    return HttpResponse(template.render({}), status=500)
