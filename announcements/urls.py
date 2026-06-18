from django.urls import path

from . import push_views as announcement_push_views
from . import views

app_name = 'announcements'

urlpatterns = [
    path('push/poll/', announcement_push_views.poll_unread, name='push_poll'),
    path('push/test/', announcement_push_views.push_test, name='push_test'),
    path('', views.announcement_list, name='list'),
    path('<int:pk>/', views.announcement_detail, name='detail'),
    path('<int:pk>/file/<str:field>/', views.announcement_file_serve, name='file'),
    path('admin/', views.admin_list, name='admin_list'),
    path('admin/create/', views.admin_create, name='admin_create'),
    path('admin/<int:pk>/edit/', views.admin_edit, name='admin_edit'),
    path('admin/<int:pk>/delete/', views.admin_delete, name='admin_delete'),
]
