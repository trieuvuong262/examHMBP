from django.urls import path

from . import views

app_name = 'announcements'

urlpatterns = [
    path('', views.announcement_list, name='list'),
    path('<int:pk>/', views.announcement_detail, name='detail'),
    path('admin/', views.admin_list, name='admin_list'),
    path('admin/create/', views.admin_create, name='admin_create'),
    path('admin/<int:pk>/edit/', views.admin_edit, name='admin_edit'),
    path('admin/<int:pk>/delete/', views.admin_delete, name='admin_delete'),
]
