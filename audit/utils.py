import re
from typing import Any

from django.http import HttpRequest

from hrm.module_permissions import MODULE_LABELS, resolve_module_from_request
from hrm.permissions import get_profile, user_role

from .models import UserActivityLog

SENSITIVE_KEY_PATTERN = re.compile(
    r'(password|passwd|token|secret|csrf|api[_-]?key|authorization|credit|cvv|pin)',
    re.IGNORECASE,
)

SKIP_PATH_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
    '/__debug__/',
)

SKIP_LOGGING_PATHS = (
    '/nhat-ky/',
)


def get_client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def should_skip_audit(request: HttpRequest) -> bool:
    path = request.path
    for prefix in SKIP_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def sanitize_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY_PATTERN.search(key):
        return '***'
    if isinstance(value, str) and len(value) > 500:
        return f'{value[:500]}…'
    return value


def sanitize_mapping(data: dict | None) -> dict:
    if not data:
        return {}
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, list):
            cleaned[key] = [
                sanitize_value(key, item) if not isinstance(item, (dict, list)) else item
                for item in value[:50]
            ]
        elif isinstance(value, dict):
            cleaned[key] = sanitize_mapping(value)
        else:
            cleaned[key] = sanitize_value(key, value)
    return cleaned


def extract_request_data(request: HttpRequest) -> dict:
    data: dict[str, Any] = {}
    if request.GET:
        data['query'] = sanitize_mapping(request.GET.dict())
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        if hasattr(request, 'POST') and request.POST:
            data['body'] = sanitize_mapping(request.POST.dict())
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type and request.body:
            try:
                import json
                payload = json.loads(request.body.decode('utf-8'))
                if isinstance(payload, dict):
                    data['json'] = sanitize_mapping(payload)
            except (UnicodeDecodeError, ValueError):
                data['json'] = {'_error': 'invalid_json'}
    return data


def infer_action(request: HttpRequest, status_code: int | None = None) -> str:
    path = request.path.lower()
    method = request.method.upper()

    if method == 'GET':
        if any(token in path for token in ('export', 'download', 'xlsx', 'csv', 'pdf')):
            return UserActivityLog.ACTION_EXPORT
        return UserActivityLog.ACTION_VIEW

    if method == 'DELETE':
        return UserActivityLog.ACTION_DELETE

    if method in {'POST', 'PUT', 'PATCH'}:
        if any(token in path for token in ('delete', 'remove', 'xoa')):
            return UserActivityLog.ACTION_DELETE
        if any(token in path for token in ('import', 'upload-bulk', 'nhap')):
            return UserActivityLog.ACTION_IMPORT
        if any(token in path for token in ('export', 'download')):
            return UserActivityLog.ACTION_EXPORT
        if any(token in path for token in ('add', 'create', 'new', 'them')):
            return UserActivityLog.ACTION_CREATE
        post = getattr(request, 'POST', None)
        if post and post.get('_method', '').upper() == 'DELETE':
            return UserActivityLog.ACTION_DELETE
        return UserActivityLog.ACTION_UPDATE

    return UserActivityLog.ACTION_OTHER


def build_summary(
    request: HttpRequest,
    action: str,
    module_label: str = '',
    object_repr: str = '',
) -> str:
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    profile = get_profile(user) if user else None
    display = ''
    if profile and profile.full_name:
        display = profile.full_name
    elif user:
        display = user.get_full_name() or user.username
    else:
        display = request.POST.get('username', 'Khách') if hasattr(request, 'POST') else 'Khách'

    target = object_repr or module_label or request.path
    action_labels = dict(UserActivityLog.ACTION_CHOICES)
    verb = action_labels.get(action, action)

    if action == UserActivityLog.ACTION_VIEW:
        return f'{display} truy cập {target}'
    if action in {UserActivityLog.ACTION_CREATE, UserActivityLog.ACTION_UPDATE, UserActivityLog.ACTION_DELETE}:
        return f'{display} {verb.lower()} · {target}'
    if action == UserActivityLog.ACTION_LOGIN:
        return f'{display} đăng nhập thành công'
    if action == UserActivityLog.ACTION_LOGOUT:
        return f'{display} đăng xuất'
    if action == UserActivityLog.ACTION_LOGIN_FAILED:
        username = request.POST.get('username', 'Không rõ') if hasattr(request, 'POST') else 'Không rõ'
        return f'Đăng nhập thất bại · tài khoản {username}'
    return f'{display} · {verb} · {target}'


def snapshot_user(user) -> dict:
    if not user or not getattr(user, 'is_authenticated', False):
        return {
            'username': '',
            'full_name': '',
            'department_name': '',
            'role': '',
        }
    profile = get_profile(user)
    department_name = profile.department.name if profile and profile.department else ''
    full_name = profile.full_name if profile and profile.full_name else user.get_full_name()
    return {
        'username': user.username,
        'full_name': full_name or '',
        'department_name': department_name,
        'role': user_role(user),
    }


def create_activity_log(
    *,
    request: HttpRequest | None = None,
    user=None,
    username_override: str = '',
    action: str,
    summary: str = '',
    module_key: str = '',
    module_label: str = '',
    path: str = '',
    method: str = '',
    query_string: str = '',
    status_code: int | None = None,
    duration_ms: int | None = None,
    url_name: str = '',
    object_type: str = '',
    object_id: str = '',
    object_repr: str = '',
    request_data: dict | None = None,
    changes: dict | None = None,
    extra: dict | None = None,
) -> UserActivityLog | None:
    snap = snapshot_user(user)
    if request is not None:
        user = user or getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            snap = snapshot_user(user)
        path = path or request.path
        method = method or request.method
        query_string = query_string if query_string != '' else request.META.get('QUERY_STRING', '')
        if not module_key:
            module_key = resolve_module_from_request(path, request.GET.get('tab')) or ''
        if not module_label and module_key:
            module_label = MODULE_LABELS.get(module_key, module_key)
        if not summary:
            summary = build_summary(request, action, module_label, object_repr)
        if request_data is None:
            request_data = extract_request_data(request)
        resolver = getattr(request, 'resolver_match', None)
        if resolver and not url_name:
            url_name = resolver.url_name or ''

    payload = {
        'user': user if user and getattr(user, 'is_authenticated', False) else None,
        'username': username_override or snap['username'] or (getattr(user, 'username', '') if user else ''),
        'full_name': snap['full_name'],
        'department_name': snap['department_name'],
        'role': snap['role'],
        'action': action,
        'module_key': module_key or '',
        'module_label': module_label or (MODULE_LABELS.get(module_key, '') if module_key else ''),
        'summary': summary[:500],
        'path': path[:500],
        'url_name': url_name[:128],
        'method': method[:10],
        'query_string': (query_string or '')[:1000],
        'status_code': status_code,
        'duration_ms': duration_ms,
        'ip_address': get_client_ip(request) if request else None,
        'user_agent': (request.META.get('HTTP_USER_AGENT', '') if request else '')[:2000],
        'referer': (request.META.get('HTTP_REFERER', '') if request else '')[:500],
        'object_type': object_type[:128],
        'object_id': str(object_id)[:64] if object_id else '',
        'object_repr': object_repr[:255],
        'request_data': request_data or {},
        'changes': changes or {},
        'extra': extra or {},
    }

    def _insert():
        return UserActivityLog.objects.create(**payload)

    return _insert()


def log_activity(
    request: HttpRequest,
    action: str,
    *,
    summary: str = '',
    object_type: str = '',
    object_id: str = '',
    object_repr: str = '',
    changes: dict | None = None,
    extra: dict | None = None,
) -> UserActivityLog | None:
    """Ghi log thủ công từ view khi cần chi tiết đối tượng."""
    return create_activity_log(
        request=request,
        action=action,
        summary=summary,
        object_type=object_type,
        object_id=object_id,
        object_repr=object_repr,
        changes=changes,
        extra=extra,
    )


def log_from_request(
    request: HttpRequest,
    response,
    duration_ms: int,
) -> UserActivityLog | None:
    if should_skip_audit(request):
        return None

    path = request.path
    if path.startswith(SKIP_LOGGING_PATHS) and request.method == 'GET':
        return None

    user = request.user
    is_auth = getattr(user, 'is_authenticated', False)
    method = request.method.upper()

    if not is_auth and method == 'GET':
        return None

    status_code = getattr(response, 'status_code', None)
    action = infer_action(request, status_code)
    module_key = resolve_module_from_request(path, request.GET.get('tab')) or ''
    module_label = MODULE_LABELS.get(module_key, '') if module_key else ''

    return create_activity_log(
        request=request,
        user=user if is_auth else None,
        action=action,
        module_key=module_key,
        module_label=module_label,
        status_code=status_code,
        duration_ms=duration_ms,
    )
