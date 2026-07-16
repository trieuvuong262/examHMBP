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
RUSTDESK_PUBLIC_HOST = os.getenv("RUSTDESK_PUBLIC_HOST", "rd.justplay.vn")
RUSTDESK_PUBLIC_KEY = os.getenv("RUSTDESK_PUBLIC_KEY", "").strip()
RUSTDESK_CLIENT_PASSWORD = os.getenv("RUSTDESK_CLIENT_PASSWORD", "").strip()
# password = bắt buộc mật khẩu cố định (deep link tự điền, không hỏi lại)
# click = không cần mật khẩu, máy đích bấm Accept
RUSTDESK_APPROVE_MODE = os.getenv("RUSTDESK_APPROVE_MODE", "password").strip().lower()
RUSTDESK_ENROLL_SECRET = os.getenv("RUSTDESK_ENROLL_SECRET", "").strip()
EQUIPMENT_SCAN_SECRET = os.getenv("EQUIPMENT_SCAN_SECRET", "").strip()
RUSTDESK_INSTALLER_URL_WIN = os.getenv("RUSTDESK_INSTALLER_URL_WIN", "").strip()
RUSTDESK_INSTALLER_URL_LINUX = os.getenv("RUSTDESK_INSTALLER_URL_LINUX", "").strip()
RUSTDESK_RENDEZVOUS_PORT = int(os.getenv("RUSTDESK_RENDEZVOUS_PORT", "21116"))
RUSTDESK_ONLINE_CHECK_ENABLED = os.getenv("RUSTDESK_ONLINE_CHECK_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
RUSTDESK_ONLINE_CHECK_TIMEOUT = float(os.getenv("RUSTDESK_ONLINE_CHECK_TIMEOUT", "3"))
RUSTDESK_ONLINE_CACHE_SEC = int(os.getenv("RUSTDESK_ONLINE_CACHE_SEC", "5"))
RUSTDESK_ONLINE_POLL_SEC = int(os.getenv("RUSTDESK_ONLINE_POLL_SEC", "5"))
RUSTDESK_WOL_ENABLED = os.getenv("RUSTDESK_WOL_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
RUSTDESK_WOL_PORT = int(os.getenv("RUSTDESK_WOL_PORT", "9"))
RUSTDESK_WOL_BROADCAST = os.getenv("RUSTDESK_WOL_BROADCAST", "").strip()
# WoL qua NAS trong LAN — VPS gọi URL này (nên dùng IP Tailscale/LAN của NAS)
RUSTDESK_WOL_RELAY_URL = os.getenv("RUSTDESK_WOL_RELAY_URL", "").strip()
RUSTDESK_WOL_RELAY_SECRET = os.getenv("RUSTDESK_WOL_RELAY_SECRET", "").strip()
RUSTDESK_WOL_RELAY_TIMEOUT = float(os.getenv("RUSTDESK_WOL_RELAY_TIMEOUT", "5"))
EQUIPMENT_NOTIFY_EMAILS = os.getenv("EQUIPMENT_NOTIFY_EMAILS", "")

# Nhân viên Thu mua (dropdown «Nhân viên Thu mua xử lý») — username cách nhau bởi dấu phẩy.
# Để trống = tự lấy theo phòng HCNS / quyền sửa Đề xuất (logic cũ).
PROCUREMENT_STAFF_USERNAMES = os.getenv(
    "PROCUREMENT_STAFF_USERNAMES",
    "vananh,thiray,Dkimchi,thuyquynh",
).strip()

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

# Giới hạn dung lượng upload (báo cáo tuần, media…) — mặc định 100MB
UPLOAD_MAX_MB = int(os.getenv('UPLOAD_MAX_MB', '100'))
UPLOAD_MAX_BYTES = UPLOAD_MAX_MB * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = UPLOAD_MAX_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = UPLOAD_MAX_BYTES
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
    'recruitment.apps.RecruitmentConfig',
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
    'surveys.apps.SurveysConfig',
    'utilities.apps.UtilitiesConfig',
    'kiotviet.apps.KiotvietConfig',
    'kho_npl.apps.KhoNplConfig',
    'san_xuat.apps.SanXuatConfig',
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
    'audit.middleware_spam.SpamIpGuardMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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
                'assessment.context_processors.portal_learning_menu_badges',
                'hrm.context_processors.portal_page_title',
                'hrm.context_processors.portal_permissions',
                'utilities.context_processors.meal_push_context',
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
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 6},
    },
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
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

# Đăng nhập — khóa tài khoản sau N lần sai; IP chỉ chặn qua blacklist / bot exploit (Quản Trị → Bảo mật đăng nhập)
LOGIN_LOCK_MAX_ATTEMPTS = int(os.getenv('LOGIN_LOCK_MAX_ATTEMPTS', '10'))
# Ngưỡng gợi ý blacklist (không còn tự chặn IP khi đăng nhập sai)
LOGIN_IP_BLOCK_MAX_ATTEMPTS = int(os.getenv('LOGIN_IP_BLOCK_MAX_ATTEMPTS', '10'))
PORTAL_IT_CONTACT = os.getenv('PORTAL_IT_CONTACT', 'Phòng IT Just Play — nhờ quản trị viên portal')

X_FRAME_OPTIONS = 'SAMEORIGIN'

# CKEditor — soạn thảo rich text + upload ảnh (ckeditor_uploader)
CKEDITOR_UPLOAD_PATH = 'ckeditor/'
CKEDITOR_UPLOAD_SLUGIFY_FILENAME = True
CKEDITOR_ALLOW_NONIMAGE_FILES = False
CKEDITOR_RESTRICT_BY_USER = True
CKEDITOR_IMAGE_BACKEND = 'pillow'
# CKEditor 4 LTS (4.25.1+) — cần license CKSource; để trống = dùng 4.22.1 bundled
CKEDITOR_LTS_LICENSE_KEY = os.getenv('CKEDITOR_LTS_LICENSE_KEY', '').strip()

CKEDITOR_CONFIGS = {
    'default': {
        'versionCheck': False,
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

# KiotViet Public API
KIOTVIET_ENABLED = env_bool('KIOTVIET_ENABLED', False)
KIOTVIET_RETAILER = os.getenv('KIOTVIET_RETAILER', '').strip()
KIOTVIET_CLIENT_ID = os.getenv('KIOTVIET_CLIENT_ID', '').strip()
KIOTVIET_CLIENT_SECRET = os.getenv('KIOTVIET_CLIENT_SECRET', '').strip()
KIOTVIET_TOKEN_URL = os.getenv('KIOTVIET_TOKEN_URL', 'https://id.kiotviet.vn/connect/token').strip()
KIOTVIET_API_BASE_URL = os.getenv('KIOTVIET_API_BASE_URL', 'https://public.kiotapi.com').strip()
# Mirror DB trung gian (bảng kv_* trên PostgreSQL portal)
KIOTVIET_USE_LOCAL_MIRROR = env_bool('KIOTVIET_USE_LOCAL_MIRROR', True)
KIOTVIET_SYNC_PAGE_SIZE = int(os.getenv('KIOTVIET_SYNC_PAGE_SIZE', '100') or '100')
KIOTVIET_API_TIMEOUT = int(os.getenv('KIOTVIET_API_TIMEOUT', '90') or '90')
KIOTVIET_API_TIMEOUT_ORDERS = int(os.getenv('KIOTVIET_API_TIMEOUT_ORDERS', '180') or '180')
# Chi nhánh hiển thị trong bảng tồn kho chi tiết hàng hóa (phân tách bằng dấu phẩy)
KIOTVIET_DETAIL_STOCK_BRANCHES = os.getenv(
    'KIOTVIET_DETAIL_STOCK_BRANCHES',
    'Chi nhánh trung tâm,Xưởng sản xuất,Đơn sản xuất',
).strip()

# Odoo ERP — đồng bộ user / menu Odoo (Phase 1)
ODOO_URL = os.getenv('ODOO_URL', 'https://erp.justplay.vn').strip().rstrip('/')
ODOO_PUBLIC_URL = os.getenv('ODOO_PUBLIC_URL', ODOO_URL or 'https://erp.justplay.vn').strip().rstrip('/')
ODOO_DB = os.getenv('ODOO_DB', 'justplay_pilot').strip()
ODOO_API_USER = os.getenv('ODOO_API_USER', '').strip()
ODOO_API_PASSWORD = os.getenv('ODOO_API_PASSWORD', '')
ODOO_VERIFY_SSL = env_bool('ODOO_VERIFY_SSL', True)
ODOO_DEFAULT_GROUPS = [
    g.strip()
    for g in os.getenv(
        'ODOO_DEFAULT_GROUPS',
        'base.group_user,stock.group_stock_user,mrp.group_mrp_user',
    ).split(',')
    if g.strip()
]
ODOO_MANAGER_GROUPS = [
    g.strip()
    for g in os.getenv(
        'ODOO_MANAGER_GROUPS',
        'stock.group_stock_manager,mrp.group_mrp_manager',
    ).split(',')
    if g.strip()
]
ODOO_SYSTEM_GROUPS = [
    g.strip()
    for g in os.getenv(
        'ODOO_SYSTEM_GROUPS',
        'base.group_system,base.group_erp_manager',
    ).split(',')
    if g.strip()
]
ODOO_ADMIN_USERNAMES = frozenset(
    u.strip().lower()
    for u in os.getenv('ODOO_ADMIN_USERNAMES', 'admin,ductn').split(',')
    if u.strip()
)
ODOO_SSO_SECRET = os.getenv('ODOO_SSO_SECRET', '').strip()
ODOO_SSO_TTL_SECONDS = int(os.getenv('ODOO_SSO_TTL_SECONDS', '120') or '120')

# NAS (Synology qua Tailscale + rclone mount trên VPS)
NAS_MOUNT_ROOT = os.getenv('NAS_MOUNT_ROOT', '/mnt/nas-portal')
NAS_RCLONE_REMOTE = os.getenv('NAS_RCLONE_REMOTE', 'synology:')
NAS_RCLONE_CONFIG = os.getenv('NAS_RCLONE_CONFIG', '/root/.config/rclone/rclone.conf')
# Phòng ban dùng share rclone riêng làm gốc (không thêm DATACHUNG/MÃ_PB)
# VD: KD-MKT:synology:KD-MKT,IT:synology:IT
NAS_DEPT_ROOT_REMOTES = os.getenv('NAS_DEPT_ROOT_REMOTES', 'KD-MKT:synology:KD-MKT')
# Mount local theo phòng ban (cùng cấu trúc remote gốc) — đọc thư mục nhanh
NAS_DEPT_MOUNT_ROOTS = os.getenv('NAS_DEPT_MOUNT_ROOTS', 'KD-MKT:/mnt/nas-kd-mkt')
NAS_LISTING_CACHE_SECONDS = int(os.getenv('NAS_LISTING_CACHE_SECONDS', '120'))
NAS_RCLONE_FAST_LIST = env_bool('NAS_RCLONE_FAST_LIST', True)
NAS_AUTO_SYNC_INTERVAL = int(os.getenv('NAS_AUTO_SYNC_INTERVAL', '60'))
NAS_BACKGROUND_SYNC_DEFAULT = env_bool('NAS_BACKGROUND_SYNC_DEFAULT', False)
# Backup Portal → NAS (database + source + media)
# Mặc định: share/thư mục gốc ``backup`` trên NAS — synology:backup
NAS_BACKUP_RCLONE_REMOTE = os.getenv('NAS_BACKUP_RCLONE_REMOTE', 'synology:backup').strip()
NAS_BACKUP_REL_PATH = os.getenv('NAS_BACKUP_REL_PATH', '').strip()
NAS_BACKUP_RETENTION_DAYS = int(os.getenv('NAS_BACKUP_RETENTION_DAYS', '30'))
# Giám sát VPS (mount /host/proc, /host/root, docker.sock vào container web)
VPS_HOST_PROC = os.getenv('VPS_HOST_PROC', '/host/proc')
VPS_HOST_ROOT = os.getenv('VPS_HOST_ROOT', '/host/root')
VPS_DOCKER_SOCKET = os.getenv('VPS_DOCKER_SOCKET', '/var/run/docker.sock')
# Giám sát NAS Synology (DSM Web API — CPU/RAM/tiến trình realtime)
NAS_DSM_URL = os.getenv('NAS_DSM_URL', 'https://100.93.5.42:5556').strip()
NAS_DSM_ACCOUNT = os.getenv('NAS_DSM_ACCOUNT', 'tailscale-justplay').strip()
NAS_DSM_PASSWORD = os.getenv('NAS_DSM_PASSWORD', '').strip()
NAS_DSM_CRED_FILE = os.getenv('NAS_DSM_CRED_FILE', '/root/.nas-cred').strip()
NAS_DSM_VERIFY_SSL = env_bool('NAS_DSM_VERIFY_SSL', False)
# Đồng bộ user Portal → Synology LDAP (Directory Server)
NAS_LDAP_SYNC_ENABLED = env_bool('NAS_LDAP_SYNC_ENABLED', False)
NAS_LDAP_HOST = os.getenv('NAS_LDAP_HOST', '').strip()
NAS_LDAP_PORT = int(os.getenv('NAS_LDAP_PORT', '636'))
NAS_LDAP_USE_SSL = env_bool('NAS_LDAP_USE_SSL', True)
NAS_LDAP_VERIFY_SSL = env_bool('NAS_LDAP_VERIFY_SSL', False)
NAS_LDAP_BASE_DN = os.getenv('NAS_LDAP_BASE_DN', 'dc=ldap,dc=justplay,dc=local').strip()
NAS_LDAP_BIND_DN = os.getenv(
    'NAS_LDAP_BIND_DN',
    'uid=root,cn=users,dc=ldap,dc=justplay,dc=local',
).strip()
NAS_LDAP_BIND_PASSWORD = os.getenv('NAS_LDAP_BIND_PASSWORD', '').strip()
NAS_LDAP_SYNC_SKIP_USERNAMES = os.getenv('NAS_LDAP_SYNC_SKIP_USERNAMES', 'admin,ductn').strip()
NAS_LDAP_DOMAIN = os.getenv('NAS_LDAP_DOMAIN', 'ldap.justplay.local').strip()
# RaiDrive / NAS ngoài (Thư viện → Tải bộ cài)
NAS_WEBDAV_PORT = int(os.getenv('NAS_WEBDAV_PORT', '5678') or '5678')
NAS_SMB_PORT = int(os.getenv('NAS_SMB_PORT', '445') or '445')
if NAS_SMB_PORT == 5678:
    NAS_SMB_PORT = 445
NAS_RDRIVE_SERVER = os.getenv('NAS_RDRIVE_SERVER', 'justplay.synology.me').strip()
NAS_RDRIVE_PORT = NAS_WEBDAV_PORT  # tương thích tên cũ = cổng WebDAV
NAS_RDRIVE_FALLBACK_SERVER = os.getenv('NAS_RDRIVE_FALLBACK_SERVER', '').strip()
NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN = os.getenv(
    'NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN',
    'e9e15707-7552-46ad-8d8e-e9962f816753',
).strip()
# Share ẩn khỏi Duyệt thư mục Portal + Quét từ NAS (share hệ thống: docker, backup, log…)
NAS_PORTAL_BROWSE_HIDDEN_SHARES = os.getenv(
    'NAS_PORTAL_BROWSE_HIDDEN_SHARES', 'docker,backup,log',
).strip()
NAS_SSH_HOST = os.getenv('NAS_SSH_HOST', '').strip()
NAS_SSH_ADMIN_USER = os.getenv('NAS_SSH_ADMIN_USER', 'admin').strip()
NAS_SSH_ADMIN_PASSWORD = os.getenv('NAS_SSH_ADMIN_PASSWORD', '').strip()
if not NAS_SSH_HOST and NAS_DSM_URL:
    from urllib.parse import urlparse

    NAS_SSH_HOST = (urlparse(NAS_DSM_URL).hostname or '').strip()
# Báo cáo tuần — đính kèm lưu trên NAS, không lưu media VPS
NAS_WEEKLY_REPORT_REL_PATH = os.getenv(
    'NAS_WEEKLY_REPORT_REL_PATH',
    '99_LUU_TRU/1.2026/BAO_CAO_TUAN',
).strip('/')
# Báo cáo ngày VP — đính kèm lưu trên NAS, không lưu media VPS
NAS_DAILY_REPORT_REL_PATH = os.getenv(
    'NAS_DAILY_REPORT_REL_PATH',
    '99_LUU_TRU/1.2026/BAO_CAO_NGAY',
).strip('/')
# Báo cáo tháng VP — đính kèm lưu trên NAS, không lưu media VPS
NAS_MONTHLY_REPORT_REL_PATH = os.getenv(
    'NAS_MONTHLY_REPORT_REL_PATH',
    '99_LUU_TRU/1.2026/BAO_CAO_THANG',
).strip('/')
# Thông báo — file PDF/video/file gốc lưu trên NAS, không lưu media VPS
NAS_ANNOUNCEMENT_REL_PATH = os.getenv(
    'NAS_ANNOUNCEMENT_REL_PATH',
    '99_LUU_TRU/1.2026/THONG_BAO',
).strip('/')
PORTAL_BACKUP_SOURCE_DIRS = os.getenv('PORTAL_BACKUP_SOURCE_DIRS', '/app,/backup-source')
PORTAL_BACKUP_INCLUDE_MEDIA = os.getenv('PORTAL_BACKUP_INCLUDE_MEDIA', '1').lower() in ('1', 'true', 'yes', 'on')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')

# Web Push (VAPID) — nhắc đặt cơm; tạo khóa: python manage.py generate_webpush_vapid_keys
WEBPUSH_VAPID_PUBLIC_KEY = os.getenv('WEBPUSH_VAPID_PUBLIC_KEY', '').strip()
WEBPUSH_VAPID_PRIVATE_KEY = os.getenv('WEBPUSH_VAPID_PRIVATE_KEY', '').strip().replace('\\n', '\n')
WEBPUSH_VAPID_CLAIMS_EMAIL = os.getenv('WEBPUSH_VAPID_CLAIMS_EMAIL', 'mailto:it@justplay.vn').strip()

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
        # Mặc định TẮT — nginx/ssl.conf xử lý HTTPS; bật Django redirect dễ gây ERR_TOO_MANY_REDIRECTS
        # khi proxy gửi X-Forwarded-Proto: http (Cloudflare Flexible, port 80, cấu hình thiếu).
        SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', False)
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
    'assessment.backends.UsernameModelBackend',
]