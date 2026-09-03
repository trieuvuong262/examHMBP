"""Giữ bộ lọc danh sách khi vào chi tiết rồi bấm Quay lại (SX + Kho NPL).

Lưu query theo từng path list trong session. Khi GET list trống mà vừa đi từ
trang cùng module (chi tiết / form), redirect lại query đã lưu. Xóa bộ lọc
(?sx_reset=1 / ?list_reset=1 hoặc GET trống từ chính trang list) thì quên query.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, QueryDict
from django.utils.http import url_has_allowed_host_and_scheme

SX_LIST_QS_SESSION_KEY = 'sx_list_qs'
SX_RESET_PARAM = 'sx_reset'
LIST_RESET_PARAM = 'list_reset'
SX_QS_MAX_LEN = 2000
SX_QS_MAX_PATHS = 80

_LIST_PREFIXES = ('/san-xuat/', '/kho-npl/')
_PK_SEGMENT = re.compile(r'/\d+(?:/|$)')
_SKIP_SUBSTRINGS = (
    '/api/',
    '/in/',
    '/them/',
    '/sua/',
    '/xuat-excel',
    '/xuat-hr',
    '/tai-lieu/',
    '/mau-excel',
    '/nhap-excel',
)
_RESET_PARAMS = frozenset({SX_RESET_PARAM, LIST_RESET_PARAM})
_DROP_KEYS = frozenset({
    * _RESET_PARAMS,
    'export',
    'download',
    'autoprint',
    'format',
    '_',
})


def _module_prefix(path: str) -> str:
    for prefix in _LIST_PREFIXES:
        if path.startswith(prefix):
            return prefix
    return ''


def is_sx_filter_list_path(path: str) -> bool:
    path = path or ''
    prefix = _module_prefix(path)
    if not prefix:
        return False
    if path.rstrip('/') == prefix.rstrip('/'):
        return False
    lower = path.lower()
    if any(token in lower for token in _SKIP_SUBSTRINGS):
        return False
    if _PK_SEGMENT.search(path):
        return False
    return True


def persistable_query(request: HttpRequest) -> str:
    params = QueryDict(mutable=True)
    for key in request.GET:
        if key in _DROP_KEYS:
            continue
        values = [v for v in request.GET.getlist(key) if str(v).strip() != '']
        if values:
            params.setlist(key, values)
    return params.urlencode()[:SX_QS_MAX_LEN]


def _store(session, path: str, query: str) -> None:
    data = dict(session.get(SX_LIST_QS_SESSION_KEY) or {})
    if query:
        data[path] = query
    else:
        data.pop(path, None)
    if len(data) > SX_QS_MAX_PATHS:
        extra = len(data) - SX_QS_MAX_PATHS
        for old_key in list(data.keys())[:extra]:
            data.pop(old_key, None)
    session[SX_LIST_QS_SESSION_KEY] = data
    session.modified = True


def saved_query_for(request: HttpRequest) -> str:
    return saved_query_for_path(request.session, request.path)


def saved_query_for_path(session, path: str) -> str:
    data = session.get(SX_LIST_QS_SESSION_KEY) or {}
    return (data.get(path) or '').strip()


def _forget(request: HttpRequest) -> None:
    _store(request.session, request.path, '')


def _referer_path(request: HttpRequest) -> str:
    raw = (request.META.get('HTTP_REFERER') or '').strip()
    if not raw:
        return ''
    parsed = urlparse(raw)
    if parsed.netloc and not url_has_allowed_host_and_scheme(
        raw, allowed_hosts={request.get_host()},
    ):
        return ''
    return parsed.path or ''


def came_from_other_sx_page(request: HttpRequest) -> bool:
    prefix = _module_prefix(request.path)
    referer_path = _referer_path(request)
    if not prefix or not referer_path.startswith(prefix):
        return False
    return referer_path.rstrip('/') != request.path.rstrip('/')


def _is_ajax(request: HttpRequest) -> bool:
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    if request.headers.get('HX-Request'):
        return True
    accept = request.headers.get('Accept') or ''
    return 'application/json' in accept and 'text/html' not in accept


def maybe_redirect_sx_list_filters(request: HttpRequest) -> HttpResponse | None:
    """Redirect GET list để khôi phục / xóa query đã lưu. None = tiếp tục view."""
    if request.method != 'GET':
        return None
    if _is_ajax(request):
        return None
    if not is_sx_filter_list_path(request.path):
        return None

    resetting = any(param in request.GET for param in _RESET_PARAMS)
    query = persistable_query(request)

    if resetting:
        if query:
            _store(request.session, request.path, query)
            target = f'{request.path}?{query}'
        else:
            _forget(request)
            target = request.path
        if request.get_full_path() != target:
            return HttpResponseRedirect(target)
        return None

    if query:
        _store(request.session, request.path, query)
        return None

    if not came_from_other_sx_page(request):
        _forget(request)
        return None

    saved = saved_query_for(request)
    if not saved:
        return None
    return HttpResponseRedirect(f'{request.path}?{saved}')
