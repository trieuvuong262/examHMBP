from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns 
from django.contrib.auth import views as auth_views
from hrm.views import MyPasswordChangeView, update_avatar
from hrm.views_guide import user_guide, user_guide_edit
from PortalJustPlay import ckeditor_upload
from PortalJustPlay.pwa import site_manifest

urlpatterns = [
    path('manifest.webmanifest', site_manifest, name='site_manifest'),
    path('admin-panel/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('huong-dan/', user_guide, name='user_guide'),
    path('huong-dan/chinh-sua/', user_guide_edit, name='user_guide_edit'),
    path('', include('assessment.urls')),
    path('cong-cu/', include('tools.urls')),
    path('training/', include('training.urls')),
    path('hr/', include('recruitment.urls')),
    path('reports/', include('reports.urls')),
    path('cong-viec/', include('tasks.urls')),
    path('yeu-cau/', include('service_requests.urls')),
    path('thiet-bi/', include('equipment.urls')),
    path('gop-y/', include('feedback.urls')),
    path('change-password/', MyPasswordChangeView.as_view(template_name='registration/password_change_form.html'), name='password_change'),
    path('change-password/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),
    path('profile/avatar/', update_avatar, name='update_avatar'),
    path('kpi/', include('kpi.urls')),
    path('announcements/', include('announcements.urls')),
    path('tai-lieu/', include('documents.urls')),
    path('thu-muc-nas/', include('nas_storage.urls')),
    path('nhat-ky/', include('audit.urls')),
    path('ckeditor/upload/', ckeditor_upload.upload, name='ckeditor_upload'),
    path('ckeditor/browse/', ckeditor_upload.browse, name='ckeditor_browse'),
]
# Cách phục vụ Media và Static chuẩn của Django
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns() # Thần chú để tự nhận diện STATICFILES_DIRS