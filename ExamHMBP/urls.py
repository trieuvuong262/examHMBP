# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Kết nối các URL từ app assessment
    path('', include('assessment.urls')), 
    
    # Thêm hệ thống đăng nhập mặc định của Django (để dùng @login_required)
    path('accounts/', include('django.contrib.auth.urls')),
]

# Cấu hình để hiển thị hình ảnh câu hỏi và bài làm từ thư mục media
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)