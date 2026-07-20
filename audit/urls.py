from django.urls import path
from django.views.generic import RedirectView

from documents.views import admin_qa_settings
from kiotviet import sync_views as kiotviet_sync_views
from zalo.views_config import zalo_oa_config_page

from . import views
from . import views_email_config
from . import views_login_security
from . import views_nas
from . import views_rustdesk
from . import views_rustdesk_setup
from . import views_vps

app_name = 'audit'

urlpatterns = [
    path('tro-ly-ai/', admin_qa_settings, name='qa_assistant'),
    path('zalo-oa/', zalo_oa_config_page, name='zalo_oa'),
    path('email/', views_email_config.email_config_page, name='email_config'),
    path('bao-mat-dang-nhap/', views_login_security.login_security_page, name='login_security'),
    path(
        'bao-mat-dang-nhap/save-config/',
        views_login_security.save_login_security_config_view,
        name='login_security_save_config',
    ),
    path('bao-mat-dang-nhap/unlock-user/<int:pk>/', views_login_security.unlock_user_login, name='unlock_user_login'),
    path('bao-mat-dang-nhap/unlock-ip/<int:pk>/', views_login_security.unlock_ip_login, name='unlock_ip_login'),
    path('', views.log_list, name='log_list'),
    path('xuat-excel/', views.log_export_excel, name='log_export_excel'),
    path('backup/', views.backup_page, name='backup_page'),
    path('backup/run/', views.backup_run, name='backup_run'),
    path('kiotviet-sync/', kiotviet_sync_views.kiotviet_sync_page, name='kiotviet_sync'),
    path('kiotviet-sync/save/', kiotviet_sync_views.kiotviet_sync_save, name='kiotviet_sync_save'),
    path('kiotviet-sync/run/', kiotviet_sync_views.kiotviet_sync_run, name='kiotviet_sync_run'),
    path('kiotviet-sync/odoo-push/', kiotviet_sync_views.kiotviet_odoo_push_run, name='kiotviet_odoo_push_run'),
    path('kiotviet-sync/status/<int:job_id>/', kiotviet_sync_views.kiotviet_sync_status, name='kiotviet_sync_status'),
    path('nas-links/', views.nas_links_index, name='nas_links'),
    path('vps/', views_vps.vps_monitor_page, name='vps_monitor'),
    path('vps/metrics/', views_vps.vps_monitor_metrics_api, name='vps_monitor_metrics'),
    path('vps/toi-uu/', views_vps.vps_monitor_optimize, name='vps_monitor_optimize'),
    path('nas/', views_nas.nas_monitor_page, name='nas_monitor'),
    path('nas/metrics/', views_nas.nas_monitor_metrics_api, name='nas_monitor_metrics'),
    path(
        'odoo/',
        RedirectView.as_view(pattern_name='odoo:redirect', permanent=False),
        name='odoo_redirect_legacy',
    ),
    path('rustdesk/', views_rustdesk.rustdesk_list, name='rustdesk_list'),
    path('rustdesk/trang-thai/', views_rustdesk.rustdesk_online_status, name='rustdesk_online_status'),
    path('rustdesk/them/', views_rustdesk.rustdesk_add, name='rustdesk_add'),
    path('rustdesk/dong-bo-thiet-bi/', views_rustdesk.rustdesk_sync_devices, name='rustdesk_sync_devices'),
    path('rustdesk/<int:pk>/wake/', views_rustdesk.rustdesk_wake, name='rustdesk_wake'),
    path('rustdesk/<int:pk>/sua/', views_rustdesk.rustdesk_edit, name='rustdesk_edit'),
    path('rustdesk/<int:pk>/xoa/', views_rustdesk.rustdesk_delete, name='rustdesk_delete'),
    path(
        'rustdesk/cai-dat/',
        RedirectView.as_view(pattern_name='documents:rustdesk_config', permanent=False),
        name='rustdesk_install',
    ),
    path('rustdesk/tai-cai-dat/', views_rustdesk_setup.rustdesk_download_setup, name='rustdesk_download_setup'),
    path('rustdesk/api/dang-ky/', views_rustdesk_setup.rustdesk_enroll_api, name='rustdesk_enroll_api'),
    path('<int:pk>/', views.log_detail, name='log_detail'),
    path('user/<int:user_id>/', views.user_timeline, name='user_timeline'),
]
