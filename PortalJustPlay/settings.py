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

if IS_LOCAL:
    default_csrf_origins = "http://127.0.0.1:8000,http://localhost:8000"
else:
    default_csrf_origins = (
        f"http://{SERVER_IP},https://{SERVER_IP},"
        f"http://{PORTAL_DOMAIN},https://{PORTAL_DOMAIN}"
    )
csrf_trusted_origins_env = os.getenv("CSRF_TRUSTED_ORIGINS", default_csrf_origins)
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in csrf_trusted_origins_env.split(",") if origin.strip()
]
for origin in (f"http://{PORTAL_DOMAIN}", f"https://{PORTAL_DOMAIN}"):
    if PORTAL_DOMAIN and origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

# Giới hạn dung lượng File Upload (Tối đa 10MB) để chống DoS
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024 


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
    'axes',
    'hrm',
    'kpi',
    'announcements',
    'documents',
    'audit.apps.AuditConfig',
    'tasks.apps.TasksConfig',
    'service_requests.apps.ServiceRequestsConfig',
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
    'axes.middleware.AxesMiddleware',
    'PortalJustPlay.middleware.ForcePasswordChangeMiddleware',
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

# ==============================================================================
# 7. CẤU HÌNH BẢO MẬT CHUYÊN SÂU KHI CHẠY PRODUCTION
# ==============================================================================
# USE_HTTPS=1 sau khi cài SSL (Let's Encrypt). Khi chưa có HTTPS, tắt COOP/HSTS
# để tránh cảnh báo console trên HTTP.
USE_HTTPS = env_bool('USE_HTTPS', False)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    AXES_FAILURE_LIMIT = int(os.getenv('AXES_FAILURE_LIMIT', '10'))

    if USE_HTTPS:
        SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', True)
        CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', True)
        SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
        SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', True)
        SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', False)
        SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
    else:
        SESSION_COOKIE_SECURE = False
        CSRF_COOKIE_SECURE = False
        SECURE_SSL_REDIRECT = False
        SECURE_HSTS_SECONDS = 0
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        SECURE_HSTS_PRELOAD = False
        SECURE_CROSS_ORIGIN_OPENER_POLICY = None
        SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = None
    
AUTHENTICATION_BACKENDS = [
    # 1. Trạm gác ngoài cùng: Bắt buộc dùng AxesBackend (đã sửa) để đếm số lần sai
    'axes.backends.AxesBackend', 
    
    # 2. Trạm gác số 2: Bộ Custom mà ní tự viết (Cho phép dùng Email hoặc Username)
    'assessment.backends.EmailOrUsernameModelBackend', 
    
    # 3. Trạm gác cuối cùng: Dự phòng mặc định của Django (Giúp tài khoản Admin/Superuser không bao giờ bị kẹt)
    'django.contrib.auth.backends.ModelBackend', 
]