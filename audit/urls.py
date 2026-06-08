from django.urls import path

from kiotviet import sync_views as kiotviet_sync_views

from . import views
from . import views_login_security

app_name = 'audit'

urlpatterns = [
    path('bao-mat-dang-nhap/', views_login_security.login_security_page, name='login_security'),
    path(
        'bao-mat-dang-nhap/save-config/',
        views_login_security.save_login_security_config_view,
        name='login_security_save_config',
    ),
    path('bao-mat-dang-nhap/unlock-user/<int:pk>/', views_login_security.unlock_user_login, name='unlock_user_login'),
    path('bao-mat-dang-nhap/unlock-ip/<int:pk>/', views_login_security.unlock_ip_login, name='unlock_ip_login'),
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
