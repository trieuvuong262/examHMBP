from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns 
from django.contrib.auth import views as auth_views
from hrm.views import MyPasswordChangeView
urlpatterns = [
    path('admin-panel/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('assessment.urls')),
    path('training/', include('training.urls')),
    path('hr/', include('recruitment.urls')),

    path('change-password/', MyPasswordChangeView.as_view(template_name='registration/password_change_form.html'), name='password_change'),
    path('change-password/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),]

# Cách phục vụ Media và Static chuẩn của Django
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns() # Thần chú để tự nhận diện STATICFILES_DIRS