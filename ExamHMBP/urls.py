# core/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from assessment.views import protected_media_serve
urlpatterns = [
    path('', include('assessment.urls')),
    path('hm-management-2026/', admin.site.urls), 
    path('accounts/', include('django.contrib.auth.urls')),
    path('training/', include('training.urls')),
    path('hr/', include('recruitment.urls')), 
    path('reports/', include('reports.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', protected_media_serve, name='protected_media'),
    ]