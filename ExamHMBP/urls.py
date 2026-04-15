# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # 1. Trang quản trị mặc định của Django (Dùng để quản lý DB cấp cao)
    path('admin/', admin.site.urls),

    # 2. Hệ thống xác thực (Login, Logout, Password Reset)
    # Django sẽ tự tìm các template trong thư mục templates/registration/
    path('accounts/', include('django.contrib.auth.urls')),

    # 3. Kết nối toàn bộ URL của ứng dụng đánh giá năng lực
    # Để trống '' để khi vào trang chủ nó sẽ dẫn thẳng vào app này
    path('', include('assessment.urls')),
]

# 4. Cấu hình để phục vụ file Media (Ảnh câu hỏi, Ảnh bài làm) trong quá trình phát triển (DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)