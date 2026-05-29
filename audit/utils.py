import re
from typing import Any

from django.http import HttpRequest

from hrm.module_permissions import MODULE_LABELS, resolve_module_from_request
from hrm.permissions import get_profile, user_role

from .models import UserActivityLog
from .summaries import build_detailed_summary, describe_post_highlights

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

# IP nội bộ Docker/proxy — không phải máy người dùng
INFRASTRUCTURE_IP_PREFIXES = (
    '127.',
    '172.17.',
    '172.18.',
    '172.19.',
    '172.20.',
    '172.21.',
    '172.22.',
)


def is_private_ip(ip: str) -> bool:
    if not ip:
        return False
    ip = ip.strip()
    if ip.startswith('192.168.'):
        return True
    if ip.startswith('10.'):
        return True
    if re.match(r'^172\.(1[6-9]|2[0-9]|3[0-1])\.', ip):
        return True
    if ip.startswith('127.') or ip == '::1':
        return True
    return False


def is_infrastructure_ip(ip: str) -> bool:
    ip = (ip or '').strip()
    if not ip or ip == '::1':
        return True
    for prefix in INFRASTRUCTURE_IP_PREFIXES:
        if ip.startswith(prefix):
            return True
    return False


def _normalize_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    ip = raw.split(',')[0].strip()
    return ip or None


def _iter_forwarded_ips(request: HttpRequest) -> list[str]:
    ips: list[str] = []
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        ips.extend(_normalize_ip(part) for part in xff.split(',') if part.strip())
    for key in ('HTTP_X_REAL_IP', 'REMOTE_ADDR'):
        ip = _normalize_ip(request.META.get(key))
        if ip:
            ips.append(ip)
    seen = set()
    ordered = []
    for ip in ips:
        if ip and ip not in seen:
            seen.add(ip)
            ordered.append(ip)
    return ordered


def get_forwarded_client_ip(request: HttpRequest) -> str | None:
    """IP client thật qua nginx — bỏ IP Docker/proxy."""
    for ip in _iter_forwarded_ips(request):
        if not is_infrastructure_ip(ip):
            return ip
    return None


def guess_device_label(request: HttpRequest, local_ip: str | None) -> str:
    if local_ip:
        return f'PC-{local_ip.rsplit(".", 1)[-1]}'

    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    if 'Windows' in ua:
        return 'Windows'
    if 'Macintosh' in ua or 'Mac OS' in ua:
        return 'Mac'
    if 'Android' in ua:
        return 'Android'
    if 'iPhone' in ua or 'iPad' in ua:
        return 'iPhone'
    if 'Linux' in ua:
        return 'Linux'
    return ''


def get_client_device_info(request: HttpRequest) -> dict:
    """
    Thu thập tên máy + IP cho nhật ký.
    - LAN: cookie/header từ trình duyệt (WebRTC)
    - IP truy cập: X-Forwarded-For / X-Real-IP (không lấy IP Docker)
    """
    hostname = (
        request.headers.get('X-Client-Hostname')
        or request.COOKIES.get('jp_hostname')
        or ''
    ).strip()

    local_ip = (
        request.headers.get('X-Client-Local-Ip')
        or request.COOKIES.get('jp_local_ip')
        or ''
    ).strip()

    if hasattr(request, 'POST'):
        hostname = hostname or (request.POST.get('client_hostname') or '').strip()
        local_ip = local_ip or (request.POST.get('client_local_ip') or '').strip()

    if local_ip and (not is_private_ip(local_ip) or is_infrastructure_ip(local_ip)):
        local_ip = ''

    public_ip = get_forwarded_client_ip(request)

    if not local_ip:
        for ip in _iter_forwarded_ips(request):
            if is_private_ip(ip) and not is_infrastructure_ip(ip):
                local_ip = ip
                break

    if not hostname:
        hostname = guess_device_label(request, local_ip or None)

    client_ip = local_ip or public_ip

    return {
        'machine_name': hostname[:128],
        'local_ip': local_ip or None,
        'public_ip': public_ip if public_ip and public_ip != local_ip else None,
        'client_ip': client_ip,
    }


def get_client_ip(request: HttpRequest) -> str | None:
    info = get_client_device_info(request)
    return info.get('client_ip')


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
    return build_detailed_summary(request, action, module_label, object_repr)


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
    device = {'local_ip': None, 'public_ip': None, 'client_ip': None, 'machine_name': ''}
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
        if not object_repr and request.method == 'POST' and resolver:
            post_hint = describe_post_highlights(request, url_name)
            if post_hint and ' · ' in post_hint:
                object_repr = post_hint.split(' · ', 1)[-1][:255]

        device = get_client_device_info(request)

    merged_extra = dict(extra or {})
    if device.get('local_ip'):
        merged_extra['client_local_ip'] = device['local_ip']
    if device.get('public_ip'):
        merged_extra['client_public_ip'] = device['public_ip']

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
        'ip_address': device.get('client_ip'),
        'machine_name': device.get('machine_name', ''),
        'user_agent': (request.META.get('HTTP_USER_AGENT', '') if request else '')[:2000],
        'referer': (request.META.get('HTTP_REFERER', '') if request else '')[:500],
        'object_type': object_type[:128],
        'object_id': str(object_id)[:64] if object_id else '',
        'object_repr': object_repr[:255],
        'request_data': request_data or {},
        'changes': changes or {},
        'extra': merged_extra,
    }

    return UserActivityLog.objects.create(**payload)


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
