"""
Django settings for ExamHMBP project.
Optimized for Security and Production.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load các biến môi trường từ file .env
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# 1. BẢO MẬT CỐT LÕI (SECURITY)
# ==============================================================================

# Lấy SECRET_KEY từ file .env (Bắt buộc phải có để chạy)
SECRET_KEY = os.getenv('SECRET_KEY')

# Bật/Tắt DEBUG qua file .env (Mặc định là False để bảo vệ Server)
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Chỉ cho phép các IP/Domain được khai báo trong .env truy cập
# Ví dụ trong .env: ALLOWED_HOSTS=127.0.0.1,localhost,hrms.hoanmy.com
allowed_hosts_env = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(',')]

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
    # Custom Apps
    'assessment',
    'training',
    'recruitment',
    'reports',
    'axes',
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
    'ExamHMBP.middleware.ForcePasswordChangeMiddleware',
]

ROOT_URLCONF = 'ExamHMBP.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'ExamHMBP.wsgi.application'


# ==============================================================================
# 3. CẤU HÌNH DATABASE
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'hrms_db'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '5432'), 
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
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'login'

X_FRAME_OPTIONS = 'SAMEORIGIN'

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'Custom',
        'toolbar_Custom': [
            ['Bold', 'Italic', 'Underline', 'Strike'],
            ['NumberedList', 'BulletedList'],
            ['JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock'],
            ['Link', 'Unlink'],
            ['RemoveFormat', 'Source'], 
            ['TextColor', 'BGColor'],
            ['Format', 'FontSize'],
        ],
        'width': '100%',
        'height': 300,
    },
}

# ==============================================================================
# 7. CẤU HÌNH BẢO MẬT CHUYÊN SÂU KHI CHẠY PRODUCTION
# ==============================================================================
if not DEBUG:
    # Tắt ép buộc HTTPS để test bằng HTTP trước
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    
    # Tắt chuyển hướng SSL
    SECURE_SSL_REDIRECT = False 
    
    # Tạm thời tắt hoặc comment dòng HSTS
    SECURE_HSTS_SECONDS = 0 
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    
    SECURE_CONTENT_TYPE_NOSNIFF = True
    AXES_FAILURE_LIMIT = 10
    
AUTHENTICATION_BACKENDS = [
    # 1. Trạm gác ngoài cùng: Bắt buộc dùng AxesBackend (đã sửa) để đếm số lần sai
    'axes.backends.AxesBackend', 
    
    # 2. Trạm gác số 2: Bộ Custom mà ní tự viết (Cho phép dùng Email hoặc Username)
    'assessment.backends.EmailOrUsernameModelBackend', 
    
    # 3. Trạm gác cuối cùng: Dự phòng mặc định của Django (Giúp tài khoản Admin/Superuser không bao giờ bị kẹt)
    'django.contrib.auth.backends.ModelBackend', 
]