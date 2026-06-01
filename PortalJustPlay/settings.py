"""
Django settings for PortalJustPlay project.
Optimized for Security and Production.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_docker_runtime() -> bool:
    return os.path.exists("/.dockerenv") or env_bool("RUNNING_IN_DOCKER", False)


def load_environment() -> None:
    """Load .env chung, sau đó .env.local (nếu có) để override khi dev máy local."""
    load_dotenv(BASE_DIR / ".env")
    local_env = BASE_DIR / ".env.local"
    if local_env.exists():
        load_dotenv(local_env, override=True)


def _normalize_csrf_origin(origin: str) -> str | None:
    origin = (origin or "").strip().rstrip("/")
    if not origin:
        return None
    if origin.startswith("http://") or origin.startswith("https://"):
        return origin
    return None


def _host_csrf_origins(host: str) -> set[str]:
    host = (host or "").strip()
    if not host or host == "*":
        return set()
    origins = {f"http://{host}", f"https://{host}"}
    if host.startswith("www."):
        bare = host[4:]
        origins.update({f"http://{bare}", f"https://{bare}"})
    elif "." in host and not all(part.isdigit() for part in host.split(".")):
        origins.update({f"http://www.{host}", f"https://www.{host}"})
    return origins


def build_csrf_trusted_origins(hosts, *, extra_from_env: str = "") -> list[str]:
    """Sinh origin http/https từ ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS trong .env."""
    origins: set[str] = set()
    for raw in extra_from_env.split(","):
        normalized = _normalize_csrf_origin(raw)
        if normalized:
            origins.add(normalized)
    for host in hosts:
        origins.update(_host_csrf_origins(host))
    return sorted(origins)


load_environment()

# local = chạy máy dev | production = chạy Docker/VPS
DJANGO_ENV = os.getenv(
    "DJANGO_ENV",
    "production" if is_docker_runtime() else "local",
).strip().lower()
IS_LOCAL = DJANGO_ENV in {"local", "development", "dev"}
IS_PRODUCTION = DJANGO_ENV in {"production", "prod"}

# ==============================================================================
# 1. BẢO MẬT CỐT LÕI (SECURITY)
# ==============================================================================

# Lấy SECRET_KEY từ file .env (production bắt buộc)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if IS_LOCAL:
        SECRET_KEY = "django-insecure-local-dev-only"
    else:
        raise ValueError("SECRET_KEY is required. Set it in .env")

# Local mặc định DEBUG=True, production mặc định DEBUG=False
DEBUG = env_bool("DEBUG", IS_LOCAL)

# Chỉ cho phép các IP/Domain được khai báo trong .env truy cập
SERVER_IP = os.getenv("SERVER_IP", "103.90.224.203")
PORTAL_DOMAIN = os.getenv("PORTAL_DOMAIN", "portal.justplay.vn").strip()
if IS_LOCAL:
    default_allowed_hosts = "127.0.0.1,localhost"
else:
    default_allowed_hosts = f"{SERVER_IP},{PORTAL_DOMAIN},127.0.0.1,localhost"
allowed_hosts_env = os.getenv("ALLOWED_HOSTS", default_allowed_hosts)
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(",") if host.strip()]
if PORTAL_DOMAIN and PORTAL_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(PORTAL_DOMAIN)
www_domain = f"www.{PORTAL_DOMAIN}" if PORTAL_DOMAIN and not PORTAL_DOMAIN.startswith("www.") else ""
if www_domain and www_domain not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(www_domain)

if IS_LOCAL:
    default_csrf_origins = "http://127.0.0.1:8000,http://localhost:8000"
else:
    default_csrf_origins = (
        f"http://{SERVER_IP},https://{SERVER_IP},"
        f"http://{PORTAL_DOMAIN},https://{PORTAL_DOMAIN}"
    )
csrf_trusted_origins_env = os.getenv("CSRF_TRUSTED_ORIGINS", default_csrf_origins)
CSRF_TRUSTED_ORIGINS = build_csrf_trusted_origins(
    ALLOWED_HOSTS,
    extra_from_env=csrf_trusted_origins_env,
)

USE_HTTPS = env_bool("USE_HTTPS", not IS_LOCAL)
_default_public_host = 'localhost:8000' if IS_LOCAL else PORTAL_DOMAIN
PORTAL_PUBLIC_BASE_URL = os.getenv(
    "PORTAL_PUBLIC_BASE_URL",
    f"{'https' if USE_HTTPS else 'http'}://{_default_public_host}",
).rstrip("/")
EQUIPMENT_TAG_HEADER = os.getenv("EQUIPMENT_TAG_HEADER", "JUSTPLAY — QUẢN LÝ THIẾT BỊ")
EQUIPMENT_AGENT_SECRET = os.getenv("EQUIPMENT_AGENT_SECRET", "")
EQUIPMENT_REQUIRE_AGENT_INSTALL = env_bool(
    "EQUIPMENT_REQUIRE_AGENT_INSTALL",
    bool(os.getenv("EQUIPMENT_AGENT_SECRET", "")),
)
EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES = os.getenv("EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES", "admin")
EQUIPMENT_AGENT_EXE_PATH = os.getenv("EQUIPMENT_AGENT_EXE_PATH", "")
EQUIPMENT_NOTIFY_EMAILS = os.getenv("EQUIPMENT_NOTIFY_EMAILS", "")

# Email — local dùng console; production cấu hình SMTP trong .env
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if IS_LOCAL else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@portal.justplay.vn")

# Giới hạn dung lượng File Upload (Tối đa 10MB) để chống DoS
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
# Admin xóa hàng loạt gửi 1 hidden field / dòng — mặc định Django chỉ 1000
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.getenv('DATA_UPLOAD_MAX_NUMBER_FIELDS', '20000'))


# ==============================================================================
# 2. CẤU HÌNH APP & MIDDLEWARE
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize', 
    'ckeditor',
    'ckeditor_uploader',
    # Custom Apps
    'assessment',
    'training',
    'recruitment',
    'reports',
    'hrm',
    'kpi',
    'announcements',
    'documents',
    'audit.apps.AuditConfig',
    'tasks.apps.TasksConfig',
    'service_requests.apps.ServiceRequestsConfig',
    'equipment.apps.EquipmentConfig',
    'feedback.apps.FeedbackConfig',
    'nas_storage.apps.NasStorageConfig',
    'tools.apps.ToolsConfig',
    'django_cleanup.apps.CleanupConfig', # 👉 Thêm dòng này vào cuối
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'PortalJustPlay.middleware.ForcePasswordChangeMiddleware',
    'equipment.middleware.AgentInstallGateMiddleware',
    'hrm.middleware.DepartmentModuleAccessMiddleware',
    'audit.middleware.ActivityAuditMiddleware',
]

ROOT_URLCONF = 'PortalJustPlay.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'announcements.context_processors.unread_announcements',
                'hrm.context_processors.portal_permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'PortalJustPlay.wsgi.application'


# ==============================================================================
# 3. CẤU HÌNH DATABASE
# ==============================================================================

DB_DEFAULTS = {
    "local": {
        "HOST": "127.0.0.1",
        "NAME": "hrms_db",
    },
    "production": {
        "HOST": "db",
        "NAME": "portaljustplay_db",
    },
}
_db = DB_DEFAULTS["production" if IS_PRODUCTION else "local"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", _db["NAME"]),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", _db["HOST"]),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}


# ==============================================================================
# 4. VALIDATION & INTERNATIONALIZATION
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True


STATIC_URL = '/static/'

# Đảm bảo đường dẫn này chuẩn đét dù có OneDrive hay không
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Thư mục gom file tĩnh cho Production
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Ép Django tìm file tĩnh đúng thứ tự
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]
# ==============================================================================
# 6. CẤU HÌNH KHÁC (AUTH, CKEDITOR)
# ==============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_REDIRECT_URL = 'login_redirect'
LOGOUT_REDIRECT_URL = 'login'

X_FRAME_OPTIONS = 'SAMEORIGIN'

# CKEditor — soạn thảo rich text + upload ảnh (ckeditor_uploader)
CKEDITOR_UPLOAD_PATH = 'ckeditor/'
CKEDITOR_UPLOAD_SLUGIFY_FILENAME = True
CKEDITOR_ALLOW_NONIMAGE_FILES = False
CKEDITOR_RESTRICT_BY_USER = True
CKEDITOR_IMAGE_BACKEND = 'pillow'

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'WordLike',
        'toolbar_WordLike': [
            ['Maximize', 'ShowBlocks', 'Source'],
            ['Undo', 'Redo'],
            ['Cut', 'Copy', 'Paste', 'PasteText', 'PasteFromWord', 'CopyFormatting'],
            ['Find', 'Replace', '-', 'SelectAll'],
            '/',
            ['Bold', 'Italic', 'Underline', 'Strike', 'Subscript', 'Superscript', '-', 'RemoveFormat'],
            ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', 'Blockquote'],
            ['JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock'],
            ['Link', 'Unlink', 'Anchor'],
            ['Image', 'Table', 'HorizontalRule', 'SpecialChar'],
            '/',
            ['Format', 'Styles'],
        ],
        'stylesSet': [
            {'name': 'Đoạn văn', 'element': 'p'},
            {'name': 'Tiêu đề 1', 'element': 'h1'},
            {'name': 'Tiêu đề 2', 'element': 'h2'},
            {'name': 'Tiêu đề 3', 'element': 'h3'},
            {'name': 'Tiêu đề 4', 'element': 'h4'},
            {'name': 'Trích dẫn', 'element': 'blockquote'},
            {'name': 'Mã nguồn', 'element': 'pre'},
        ],
        'format_tags': 'p;h1;h2;h3;h4;h5;h6;pre;address',
        'width': '100%',
        'height': 460,
        'language': 'vi',
        'filebrowserUploadUrl': '/ckeditor/upload/',
        'filebrowserBrowseUrl': '/ckeditor/browse/',
        'filebrowserImageUploadUrl': '/ckeditor/upload/',
        'extraPlugins': (
            'uploadimage,image2,tableresize,tabletools,tableselection,'
            'liststyle,pastefromword,copyformatting,stylescombo,autogrow'
        ),
        'removePlugins': 'exportpdf,image',
        'allowedContent': True,
        'forcePasteAsPlainText': False,
        'pasteFromWordRemoveFontStyles': False,
        'pasteFromWordRemoveStyles': False,
        'contentsCss': ['/static/css/ckeditor-content.css'],
    },
}

# Gemini AI — Hỏi đáp Thư viện (đặt key trong .env, không commit)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# NAS (Synology qua Tailscale + rclone mount trên VPS)
NAS_MOUNT_ROOT = os.getenv('NAS_MOUNT_ROOT', '/mnt/nas-portal')
NAS_RCLONE_REMOTE = os.getenv('NAS_RCLONE_REMOTE', 'synology:DATACHUNG')
NAS_RCLONE_CONFIG = os.getenv('NAS_RCLONE_CONFIG', '/root/.config/rclone/rclone.conf')
NAS_AUTO_SYNC_INTERVAL = int(os.getenv('NAS_AUTO_SYNC_INTERVAL', '15'))
NAS_SHARE_EXPIRE_DAYS = int(os.getenv('NAS_SHARE_EXPIRE_DAYS', '30'))
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')

# ==============================================================================
# 7. CẤU HÌNH BẢO MẬT CHUYÊN SÂU KHI CHẠY PRODUCTION
# ==============================================================================
# USE_HTTPS=1 sau khi cài SSL (Let's Encrypt). Khi chưa có HTTPS, tắt COOP/HSTS
# để tránh cảnh báo console trên HTTP.
USE_HTTPS = env_bool('USE_HTTPS', False)

if not DEBUG:
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'

    if USE_HTTPS:
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
        SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', True)
        CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', True)
        SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
        SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
        SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)
        SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
    else:
        # HTTP — không đánh dấu cookie Secure, không ép HTTPS (tránh mất CSRF/session)
        SESSION_COOKIE_SECURE = False
        CSRF_COOKIE_SECURE = False
        SECURE_SSL_REDIRECT = False
        SECURE_HSTS_SECONDS = 0
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        SECURE_HSTS_PRELOAD = False
        SECURE_CROSS_ORIGIN_OPENER_POLICY = None
        SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = None
    
AUTHENTICATION_BACKENDS = [
    'assessment.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]