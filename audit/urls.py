from django.urls import path

from kiotviet import sync_views as kiotviet_sync_views

from . import views

app_name = 'audit'

urlpatterns = [
    path('', views.log_list, name='log_list'),
    path('backup/', views.backup_page, name='backup_page'),
    path('backup/run/', views.backup_run, name='backup_run'),
    path('kiotviet-sync/', kiotviet_sync_views.kiotviet_sync_page, name='kiotviet_sync'),
    path('kiotviet-sync/save/', kiotviet_sync_views.kiotviet_sync_save, name='kiotviet_sync_save'),
    path('kiotviet-sync/run/', kiotviet_sync_views.kiotviet_sync_run, name='kiotviet_sync_run'),
    path('kiotviet-sync/status/<int:job_id>/', kiotviet_sync_views.kiotviet_sync_status, name='kiotviet_sync_status'),
    path('nas-links/', views.nas_links_index, name='nas_links'),
    path('<int:pk>/', views.log_detail, name='log_detail'),
    path('user/<int:user_id>/', views.user_timeline, name='user_timeline'),
]
