"""Phát hiện bot quét / exploit — chặn IP ngay lần đầu."""

from __future__ import annotations

import re
from typing import Iterator

from django.http import HttpRequest

# --- Field / query key rác (bot form) ---
SUSPICIOUS_POST_FIELD_KEY = re.compile(
    r'^(?:\d{1,4}|content\d+|[0-9a-f]{4,12})$',
    re.IGNORECASE,
)

# --- Path quét (CMS, Java, PHP, DevOps, router…) ---
EXPLOIT_PATH_RE = re.compile(
    r'(?:'
    # Extensions / backup
    r'\.(?:jsp|jspx|php|phps|phtml|asp|aspx|ashx|asmx|cgi|pl|py|rb|env|git|svn|bak|sql|dump|old|orig|save|swp|war|jar|class|inc|cfg|ini|log|yml|yaml|toml|pem|key|crt|cer|pfx|p12|db|sqlite|mdb)'
    r'|/\.env|/\.git|/\.svn|/\.hg|/\.DS_Store|/\.htaccess|/\.htpasswd|/web\.config|/crossdomain\.xml'
    # WordPress / CMS
    r'|wp-admin|wp-login|wp-content|wp-includes|xmlrpc\.php|wlwmanifest\.xml|readme\.html'
    r'|phpmyadmin|pma/|adminer|mysqlmanager|myadmin'
    r'|drupal|joomla|magento|prestashop|opencart|typo3|umbraco'
    # Java / Tomcat / Spring
    r'|serverinfo|jmxinvoker|invoker/|jmx-console|web-console|manager/html|host-manager'
    r'|axis2|struts|faces/javax|springboot|actuator|/hystrix|/jolokia|/heapdump'
    r'|web-inf|meta-inf|WEB-INF|META-INF'
    # Dev / framework probes
    r'|phpinfo|info\.php|test\.php|shell\.php|cmd\.php|backdoor|webshell|c99|r57'
    r'|vendor/phpunit|eval-stdin\.php|think\\app|pearcmd|laravel|symfony|yii|zend'
    r'|_profiler|_ignition|telescope|horizon/|nova/|debug/default|elmah\.axd'
    r'|graphql|api/graphql|api/swagger|swagger-ui|api-docs|openapi\.json'
    # Search / infra
    r'|/solr/|/elasticsearch/|/_cat/|/_nodes/|/kibana/|/grafana/'
    r'|/jenkins/|/gitlab/|/nexus/|/artifactory/|/sonarqube/'
    r'|/console/|/administrator/|/phpmy|/mysql/|/redis/|/mongodb/'
    # Network / IoT / router
    r'|cgi-bin/|boaform|setup\.cgi|apply\.cgi|HNAP1|evox/about|sdk/|systembc'
    r'|containers/json|docker/|portainer/|kubernetes/|k8s/'
    # Mail / VPN / RDP probes
    r'|owa/|autodiscover|exchange/|remote/login|rdweb/|vpn/|pulse/secure'
    # Path traversal encoded
    r'|%2e%2e|%252e|/etc/passwd|/proc/self|win\.ini|boot\.ini'
    r')',
    re.IGNORECASE,
)

PATH_TRAVERSAL_RE = re.compile(
    r'(?:\.\./|\.\.\\|%2e%2e%2f|%2e%2e/|\.\.%2f|%252e%252e)',
    re.IGNORECASE,
)

BLOCKED_HTTP_METHODS = frozenset({'TRACE', 'TRACK', 'DEBUG', 'CONNECT'})

SCANNER_USER_AGENT_RE = re.compile(
    r'(?:'
    r'zap|owasp|nikto|sqlmap|nessus|acunetix|wpscan|masscan|nmap|dirbuster|gobuster|ffuf|feroxbuster'
    r'|burpsuite|burp\s|openvas|qualys|rapid7|metasploit|havij|pangolin'
    r'|netsparker|appscan|webinspect|arachni|w3af|skipfish|whatweb'
    r')',
    re.IGNORECASE,
)

SCRIPTING_CLIENT_UA_RE = re.compile(
    r'(?:'
    r'python-requests|aiohttp|httpx/|urllib|libwww-perl|lwp-trivial|wget/|curl/|go-http-client'
    r'|java/|apache-httpclient|okhttp|scrapy|httpclient|ruby|perl|php/|node-fetch|axios/'
    r'|postmanruntime|insomnia/|httpie/|powershell/'
    r')',
    re.IGNORECASE,
)

MALICIOUS_PAYLOAD_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PHP / shell
    re.compile(r'<\?php', re.IGNORECASE),
    re.compile(r'(?:shell_exec|base64_decode|passthru|proc_open|popen|assert)\s*\(', re.IGNORECASE),
    re.compile(r'(?:eval|system|exec)\s*\(\s*[\'"]', re.IGNORECASE),
    re.compile(r'php://(?:input|filter|expect|data)|data://text/', re.IGNORECASE),
    # JS / template / RSC
    re.compile(r'__proto__|prototype\s*pollution|constructor\s*\[', re.IGNORECASE),
    re.compile(r'\{\{[\s=]|\{%|%\}', re.IGNORECASE),
    re.compile(r'\$ACTION[_\s]|resolved_model|\$@0', re.IGNORECASE),
    re.compile(r'class\.module\.classLoader', re.IGNORECASE),
    # Log4j / JNDI
    re.compile(r'\$\{jndi:(?:ldap|rmi|dns|nis)', re.IGNORECASE),
    re.compile(r'jndi:(?:ldap|rmi)://', re.IGNORECASE),
    # SQLi
    re.compile(r'union\s+(?:all\s+)?select', re.IGNORECASE),
    re.compile(r'(?:\'|")\s*or\s+[\'"]?\d+[\'"]?\s*=\s*[\'"]?\d+', re.IGNORECASE),
    re.compile(r'information_schema|@@version|sleep\s*\(|benchmark\s*\(|waitfor\s+delay', re.IGNORECASE),
    re.compile(r';\s*(?:drop|alter|truncate)\s+table', re.IGNORECASE),
    # XSS
    re.compile(r'<script[\s>]|javascript:|onerror\s*=|onload\s*=', re.IGNORECASE),
    re.compile(r'<iframe|<embed|<object', re.IGNORECASE),
    # Traversal / LFI
    re.compile(r'/etc/passwd|/etc/shadow|boot\.ini|win\.ini', re.IGNORECASE),
    re.compile(r'KHdnZXQ|L2V0Yy9wYXNzd2Q', re.IGNORECASE),
    # Command injection
    re.compile(r'(?:;|\||&&)\s*(?:wget|curl|nc\s|bash\s|/bin/sh|cmd\.exe)', re.IGNORECASE),
    re.compile(r'\$\([^)]+\)|`[^`]+`', re.IGNORECASE),
    re.compile(r'cmd\.exe|powershell\s+-(?:enc|e)\b', re.IGNORECASE),
    # NoSQL / LDAP
    re.compile(r'\$where|\$gt\s*:|"\$ne"\s*:', re.IGNORECASE),
    # Misc scanners
    re.compile(r'bxss\.me|oast\.|interact\.sh|burpcollaborator', re.IGNORECASE),
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
    '/favicon.ico',
})

# Portal route hợp lệ — không chặn UA script trên các path này (health/agent)
SCRIPTING_UA_ALLOW_PREFIXES = (
    '/thiet-bi/api/',
    '/thiet-bi/agent/',
)


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
    for header_key in (
        'HTTP_REFERER',
        'HTTP_X_FORWARDED_FOR',
        'HTTP_X_ORIGINAL_URL',
        'HTTP_X_REWRITE_URL',
    ):
        val = request.META.get(header_key, '')
        if val:
            yield str(val)
    if request.GET:
        for key, value in request.GET.items():
            yield str(key)
            yield str(value)
    if request.POST:
        for key, value in request.POST.items():
            yield str(key)
            yield str(value)
    content_type = (getattr(request, 'headers', {}) or {}).get('Content-Type', '')
    if hasattr(content_type, 'lower'):
        content_type = content_type.lower()
    body = getattr(request, 'body', b'') or b''
    if request.method in {'POST', 'PUT', 'PATCH'} and body:
        if 'json' in content_type or 'text/' in content_type or 'form' in content_type or not content_type:
            try:
                yield body.decode('utf-8', errors='ignore')[:12000]
            except Exception:
                pass


def _match_payloads(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in MALICIOUS_PAYLOAD_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern[:48])
    return hits


def _detect_blocked_method(request: HttpRequest) -> tuple[bool, list[str]]:
    method = (request.method or '').upper()
    if method in BLOCKED_HTTP_METHODS:
        return True, [method]
    return False, []


def _detect_exploit_path(request: HttpRequest) -> tuple[bool, list[str]]:
    path = request.path or ''
    if not path or path == '/':
        return False, []
    if EXPLOIT_PATH_RE.search(path) or PATH_TRAVERSAL_RE.search(path):
        return True, [path[:120]]
    return False, []


def _detect_scanner_user_agent(request: HttpRequest) -> tuple[bool, list[str]]:
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    if SCANNER_USER_AGENT_RE.search(ua):
        return True, [ua[:100]]
    return False, []


def _detect_scripting_client(request: HttpRequest) -> tuple[bool, list[str]]:
    path = request.path or ''
    for prefix in SCRIPTING_UA_ALLOW_PREFIXES:
        if path.startswith(prefix):
            return False, []
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    if SCRIPTING_CLIENT_UA_RE.search(ua):
        return True, [ua[:100]]
    if request.method in {'POST', 'PUT', 'PATCH'} and ua.strip() and len(ua.strip()) < 8:
        return True, ['short-ua']
    return False, []


def _detect_suspicious_query_keys(request: HttpRequest) -> tuple[bool, list[str]]:
    if not request.GET:
        return False, []
    suspicious = [key for key in request.GET.keys() if SUSPICIOUS_POST_FIELD_KEY.match(str(key))]
    if len(suspicious) >= 2:
        return True, suspicious[:8]
    if len(suspicious) == 1 and len(request.GET) <= 2:
        val = str(request.GET.get(suspicious[0], ''))
        if _match_payloads(val) or _match_payloads(str(suspicious[0])):
            return True, suspicious
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
    for key in suspicious_keys:
        if _match_payloads(str(post.get(key, ''))):
            return True, [key]
    return False, []


def _detect_login_abuse(request: HttpRequest) -> tuple[bool, list[str]]:
    if request.method != 'POST':
        return False, []

    post = getattr(request, 'POST', None)
    if not post:
        return False, []

    username = str(post.get('username', '') or '')
    password = str(post.get('password', '') or '')
    login_markers = ('zap', 'admin', 'root', 'test', 'scanner', 'exploit')
    uname_lower = username.strip().lower()
    if uname_lower in login_markers or uname_lower.endswith('@example.com'):
        if _match_payloads(password) or '{{' in password or len(password) > 120:
            return True, [f'user:{username[:40]}']

    for label, value in (('user', username), ('pass', password)):
        if not value:
            continue
        hits = _match_payloads(value)
        if hits:
            return True, [f'{label}:{value[:60]}']
        if '{{' in value and '}}' in value:
            return True, [f'{label}:template-injection']
        if '${' in value and '}' in value:
            return True, [f'{label}:jndi-injection']

    for key in post.keys():
        val = str(post.get(key, '') or '')
        if not val:
            continue
        if key.isdigit() or SUSPICIOUS_POST_FIELD_KEY.match(key):
            if any(
                token in val
                for token in ('__proto__', 'resolved_model', '$@0', '$ACTION', 'constructor')
            ):
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
    Quét path, method, UA, payload, form rác, login exploit…
    """
    if should_skip_spam_guard(request):
        return False, '', []

    is_auth = _request_is_authenticated(request)

    for detector, reason in (
        (_detect_blocked_method, 'blocked_method'),
        (_detect_exploit_path, 'exploit_path'),
    ):
        hit, details = detector(request)
        if hit:
            return True, reason, details

    if not is_auth:
        checks = (
            (_detect_scanner_user_agent, 'scanner_ua'),
            (_detect_garbage_form_fields, 'garbage_form_fields'),
            (_detect_login_abuse, 'login_abuse'),
            (_detect_suspicious_query_keys, 'garbage_query_keys'),
            (_detect_malicious_payload, 'malicious_payload'),
            (_detect_scripting_client, 'scripting_client'),
        )
        for detector, reason in checks:
            hit, details = detector(request)
            if hit:
                return True, reason, details

    return False, '', []


def detect_form_field_spam(request: HttpRequest) -> tuple[bool, list[str]]:
    """Tương thích code cũ."""
    is_threat, reason, details = detect_security_scan(request)
    if is_threat and reason in {
        'garbage_form_fields',
        'garbage_query_keys',
        'malicious_payload',
        'login_abuse',
    }:
        return True, details
    return False, []
