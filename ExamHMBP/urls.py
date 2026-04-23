from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns # Thêm dòng này

urlpatterns = [
    path('admin-panel/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('assessment.urls')),
    path('training/', include('training.urls')),
    path('hr/', include('recruitment.urls')),
]

# Cách phục vụ Media và Static chuẩn của Django
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns() # Thần chú để tự nhận diện STATICFILES_DIRS