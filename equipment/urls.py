from django.urls import path
from django.views.generic.base import RedirectView

from . import views

app_name = 'equipment'

_it = {'equipment_scope': 'it'}
_production = {'equipment_scope': 'production'}

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='equipment:dashboard_it', permanent=False), name='dashboard'),
    path('it/', views.dashboard, {**_it}, name='dashboard_it'),
    path('it/danh-sach/', views.device_list, {**_it}, name='device_list_it'),
    path('it/them/', views.device_add, {**_it}, name='device_add_it'),
    path('it/ho-tro/', views.it_repair_list, {**_it}, name='it_repair_list_it'),
    path('it/ho-tro/<int:pk>/', views.it_repair_detail, {**_it}, name='it_repair_detail_it'),
    path('it/nhap-xuat/', views.import_export_hub, {**_it}, name='import_export_hub_it'),
    path('it/loai-thiet-bi/', views.category_list, {**_it}, name='category_list_it'),
    path('it/loai-thiet-bi/them/', views.category_add, {**_it}, name='category_add_it'),
    path('it/loai-thiet-bi/<int:pk>/sua/', views.category_edit, {**_it}, name='category_edit_it'),
    path('it/loai-thiet-bi/<int:pk>/xoa/', views.category_delete, {**_it}, name='category_delete_it'),
    path('it/xuat-excel/', views.export_devices, {**_it}, name='export_devices_it'),
    path('it/file-mau/', views.download_sample, {**_it}, name='download_sample_it'),
    path('it/nhap-excel/', views.import_devices, {**_it}, name='import_devices_it'),
    path('it/xoa-hang-loat/', views.delete_bulk_devices, {**_it}, name='delete_bulk_devices_it'),

    path('san-xuat/', views.dashboard, {**_production}, name='dashboard_production'),
    path('san-xuat/danh-sach/', views.device_list, {**_production}, name='device_list_production'),
    path('san-xuat/them/', views.device_add, {**_production}, name='device_add_production'),
    path('san-xuat/ho-tro/', views.it_repair_list, {**_production}, name='it_repair_list_production'),
    path('san-xuat/ho-tro/<int:pk>/', views.it_repair_detail, {**_production}, name='it_repair_detail_production'),
    path('san-xuat/nhap-xuat/', views.import_export_hub, {**_production}, name='import_export_hub_production'),
    path('san-xuat/loai-thiet-bi/', views.category_list, {**_production}, name='category_list_production'),
    path('san-xuat/loai-thiet-bi/them/', views.category_add, {**_production}, name='category_add_production'),
    path('san-xuat/loai-thiet-bi/<int:pk>/sua/', views.category_edit, {**_production}, name='category_edit_production'),
    path('san-xuat/loai-thiet-bi/<int:pk>/xoa/', views.category_delete, {**_production}, name='category_delete_production'),
    path('san-xuat/xuat-excel/', views.export_devices, {**_production}, name='export_devices_production'),
    path('san-xuat/file-mau/', views.download_sample, {**_production}, name='download_sample_production'),
    path('san-xuat/nhap-excel/', views.import_devices, {**_production}, name='import_devices_production'),
    path('san-xuat/xoa-hang-loat/', views.delete_bulk_devices, {**_production}, name='delete_bulk_devices_production'),

    path('danh-sach/', RedirectView.as_view(pattern_name='equipment:device_list_it', permanent=False), name='device_list'),
    path('ho-tro/', RedirectView.as_view(pattern_name='equipment:it_repair_list_it', permanent=False), name='it_repair_list'),
    path('ho-tro/<int:pk>/', views.legacy_it_repair_detail, name='it_repair_detail'),
    path('them/', RedirectView.as_view(pattern_name='equipment:device_add_it', permanent=False), name='device_add'),
    path('nhap-xuat/', RedirectView.as_view(pattern_name='equipment:import_export_hub_it', permanent=False), name='import_export_hub'),
    path('loai-thiet-bi/', RedirectView.as_view(pattern_name='equipment:category_list_it', permanent=False), name='category_list'),
    path('loai-thiet-bi/them/', RedirectView.as_view(pattern_name='equipment:category_add_it', permanent=False), name='category_add'),
    path('loai-thiet-bi/<int:pk>/sua/', RedirectView.as_view(pattern_name='equipment:category_edit_it', permanent=False), name='category_edit'),
    path('loai-thiet-bi/<int:pk>/xoa/', RedirectView.as_view(pattern_name='equipment:category_delete_it', permanent=False), name='category_delete'),
    path('xuat-excel/', RedirectView.as_view(pattern_name='equipment:export_devices_it', permanent=False), name='export_devices'),
    path('file-mau/', RedirectView.as_view(pattern_name='equipment:download_sample_it', permanent=False), name='download_sample'),
    path('nhap-excel/', RedirectView.as_view(pattern_name='equipment:import_devices_it', permanent=False), name='import_devices'),
    path('xoa-hang-loat/', RedirectView.as_view(pattern_name='equipment:delete_bulk_devices_it', permanent=False), name='delete_bulk_devices'),

    path('qr/<str:device_key>/', views.device_qr_public, name='device_qr_public'),
    path('<uuid:device_id>/', views.device_detail_manage, name='device_detail_manage'),
    path('<uuid:device_id>/sua/', views.device_edit, name='device_edit'),
    path('<uuid:device_id>/lich-su/', views.device_history, name='device_history'),
    path('<uuid:device_id>/lich-su-cap-nhat/', views.device_update_history, name='device_update_history'),
    path('api/agent-report/', views.api_agent_report, name='api_agent_report'),
    path('api/agent-poll/', views.api_agent_poll, name='api_agent_poll'),
    path('agent/', views.agent_guide, name='agent_guide'),
    path('agent/yeu-cau-cai/', views.agent_install_gate, name='agent_install_gate'),
    path('agent/xac-nhan-chung/', views.agent_confirm_shared_pc, name='agent_confirm_shared_pc'),
    path('agent/tai-cai-dat/', views.agent_download_installer, name='agent_download_installer'),
    path('agent/exe/', views.agent_serve_exe, name='agent_serve_exe'),
    path('agent/cai-portal-app/', views.agent_portal_app_install, name='agent_portal_app_install'),
    path('agent/hoan-tat/', views.agent_install_done, name='agent_install_done'),
    path('agent/trang-thai/', views.api_agent_install_status, name='api_agent_install_status'),
    path('agent/ping/', views.agent_config_ping, name='agent_config_ping'),
    path('agent/quet/', views.request_agent_rescan, name='request_agent_rescan'),
]
