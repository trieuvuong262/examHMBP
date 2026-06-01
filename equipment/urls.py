from django.urls import path

from . import views

app_name = 'equipment'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('danh-sach/', views.device_list, name='device_list'),
    path('them/', views.device_add, name='device_add'),
    path('<uuid:device_id>/', views.device_detail_manage, name='device_detail_manage'),
    path('<uuid:device_id>/sua/', views.device_edit, name='device_edit'),
    path('<uuid:device_id>/lich-su/', views.device_history, name='device_history'),
    path('qr/<uuid:device_id>/', views.device_qr_public, name='device_qr_public'),
    path('xuat-excel/', views.export_devices, name='export_devices'),
    path('nhap-excel/', views.import_devices, name='import_devices'),
    path('api/agent-report/', views.api_agent_report, name='api_agent_report'),
]
