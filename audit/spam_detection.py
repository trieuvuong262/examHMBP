"""Phát hiện bot quét / exploit — chặn IP ngay lần đầu."""

from __future__ import annotations

import re
from typing import Iterator

from django.http import HttpRequest

# VPS 09/06/2026: field 0, 1, 2, 4d2199, content29
SUSPICIOUS_POST_FIELD_KEY = re.compile(
    r'^(?:\d{1,4}|content\d+|[0-9a-f]{4,12})$',
    re.IGNORECASE,
)

EXPLOIT_PATH_RE = re.compile(
    r'(?:'
    r'\.(?:jsp|jspx|php|asp|aspx|cgi|env|git|svn|bak|sql|war|jar)'
    r'|wp-admin|wp-login|wp-content|xmlrpc\.php|phpmyadmin'
    r'|serverinfo|jmxinvoker|invoker/servlet|web-inf|meta-inf'
    r'|/solr/|/actuator/|/console/|/struts/|/jenkins/'
    r'|cgi-bin/|\.aws/|/administrator/'
    r')',
    re.IGNORECASE,
)

SCANNER_USER_AGENT_RE = re.compile(
    r'(?:zap|owasp|nikto|sqlmap|nessus|acunetix|wpscan|masscan|nmap|dirbuster|gobuster)',
    re.IGNORECASE,
)

MALICIOUS_PAYLOAD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'<\?php', re.IGNORECASE),
    re.compile(r'(?:shell_exec|base64_decode|passthru|proc_open|popen)\s*\(', re.IGNORECASE),
    re.compile(r'(?:eval|system|exec)\s*\(\s*[\'"]', re.IGNORECASE),
    re.compile(r'__proto__|prototype\s*pollution', re.IGNORECASE),
    re.compile(r'\{\{[\s=]', re.IGNORECASE),
    re.compile(r'\$ACTION[_\s]', re.IGNORECASE),
    re.compile(r'resolved_model', re.IGNORECASE),
    re.compile(r'\$@0', re.IGNORECASE),
    re.compile(r'KHdnZXQ', re.IGNORECASE),
    re.compile(r'union\s+select', re.IGNORECASE),
    re.compile(r'/etc/passwd', re.IGNORECASE),
    re.compile(r'cmd\.exe|powershell\s+-', re.IGNORECASE),
)

SPAM_GUARD_SKIP_PATH_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
    '/thiet-bi/api/',
    '/thiet-bi/agent/',
    '/.well-known/acme-challenge/',
    '/ckeditor/',
)

SPAM_GUARD_SKIP_PATHS = frozenset({
    '/sw.js',
    '/manifest.webmanifest',
    '/robots.txt',
})


def should_skip_spam_guard(request: HttpRequest) -> bool:
    path = request.path or ''
    for prefix in SPAM_GUARD_SKIP_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return path in SPAM_GUARD_SKIP_PATHS


def _request_is_authenticated(request: HttpRequest) -> bool:
    user = getattr(request, 'user', None)
    return bool(user is not None and getattr(user, 'is_authenticated', False))


def _iter_request_chunks(request: HttpRequest) -> Iterator[str]:
    yield request.path or ''
    query = request.META.get('QUERY_STRING', '')
    if query:
        yield query
    if request.GET:
        for key, value in request.GET.items():
            yield str(key)
            yield str(value)
    if request.POST:
        for key, value in request.POST.items():
            yield str(key)
            yield str(value)
    content_type = (request.headers.get('Content-Type') or '').lower()
    if request.method == 'POST' and 'application/json' in content_type and request.body:
        try:
            yield request.body.decode('utf-8', errors='ignore')[:8000]
        except Exception:
            pass


def _match_payloads(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in MALICIOUS_PAYLOAD_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern[:48])
    return hits


def _detect_exploit_path(request: HttpRequest) -> tuple[bool, list[str]]:
    path = (request.path or '').lower()
    if not path or path == '/':
        return False, []
    if EXPLOIT_PATH_RE.search(path):
        return True, [request.path[:120]]
    return False, []


def _detect_scanner_user_agent(request: HttpRequest) -> tuple[bool, list[str]]:
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    if SCANNER_USER_AGENT_RE.search(ua):
        return True, [ua[:100]]
    return False, []


def _detect_garbage_form_fields(request: HttpRequest) -> tuple[bool, list[str]]:
    if request.method != 'POST':
        return False, []

    post = getattr(request, 'POST', None)
    if not post:
        return False, []

    keys = list(post.keys())
    if not keys:
        return False, []

    suspicious_keys = [key for key in keys if SUSPICIOUS_POST_FIELD_KEY.match(key)]
    if not suspicious_keys:
        return False, []

    has_csrf = 'csrfmiddlewaretoken' in keys
    if not has_csrf:
        return True, suspicious_keys
    if len(suspicious_keys) >= 3:
        return True, suspicious_keys
    return False, []


def _detect_login_abuse(request: HttpRequest) -> tuple[bool, list[str]]:
    if request.method != 'POST':
        return False, []

    post = getattr(request, 'POST', None)
    if not post:
        return False, []

    username = str(post.get('username', '') or '')
    password = str(post.get('password', '') or '')
    if username.strip().upper() == 'ZAP' or 'zap' in username.lower().split():
        return True, [f'user:{username[:40]}']

    for label, value in (('user', username), ('pass', password)):
        if not value:
            continue
        hits = _match_payloads(value)
        if hits:
            return True, [f'{label}:{value[:60]}']
        if '{{' in value and '}}' in value:
            return True, [f'{label}:template-injection']

    for key in post.keys():
        val = str(post.get(key, '') or '')
        if not val:
            continue
        if key.isdigit() or SUSPICIOUS_POST_FIELD_KEY.match(key):
            if any(token in val for token in ('__proto__', 'resolved_model', '$@0', '$ACTION')):
                return True, [f'{key}:{val[:80]}']
    return False, []


def _detect_malicious_payload(request: HttpRequest) -> tuple[bool, list[str]]:
    hits: list[str] = []
    for chunk in _iter_request_chunks(request):
        for marker in _match_payloads(chunk):
            if marker not in hits:
                hits.append(marker)
            if len(hits) >= 5:
                return True, hits
    if hits:
        return True, hits
    return False, []


def detect_security_scan(request: HttpRequest) -> tuple[bool, str, list[str]]:
    """
    Trả (is_threat, reason_code, details).
    Quét path JSP/PHP, payload shell, ZAP, prototype pollution, form rác…
    """
    if should_skip_spam_guard(request):
        return False, '', []

    is_auth = _request_is_authenticated(request)

    hit, details = _detect_exploit_path(request)
    if hit:
        return True, 'exploit_path', details

    if not is_auth:
        hit, details = _detect_scanner_user_agent(request)
        if hit:
            return True, 'scanner_ua', details

        hit, details = _detect_garbage_form_fields(request)
        if hit:
            return True, 'garbage_form_fields', details

        hit, details = _detect_login_abuse(request)
        if hit:
            return True, 'login_abuse', details

        hit, details = _detect_malicious_payload(request)
        if hit:
            return True, 'malicious_payload', details

    return False, '', []


def detect_form_field_spam(request: HttpRequest) -> tuple[bool, list[str]]:
    """Tương thích code cũ — chỉ kiểm tra field form rác."""
    is_threat, reason, details = detect_security_scan(request)
    if is_threat and reason == 'garbage_form_fields':
        return True, details
    if is_threat and reason in {'malicious_payload', 'login_abuse'}:
        return True, details
    return False, []
