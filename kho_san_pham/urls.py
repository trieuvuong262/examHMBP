from django.urls import path

from kho_san_pham import views, views_code_settings, views_stock

app_name = 'kho_san_pham'

urlpatterns = [
    path('', views.hub_redirect, name='hub'),
    path('ton-kho/', views_stock.stock_list, name='stock_list'),
    path('danh-muc/', views.product_list, name='product_list'),
    path('danh-muc/xuat-excel/', views.product_export, name='product_export'),
    path('danh-muc/mau-excel/', views.product_import_template, name='product_import_template'),
    path('danh-muc/nhap-excel/', views.product_import, name='product_import'),
    path('danh-muc/nhap-ma-ke-toan/', views.product_import_accounting, name='product_import_accounting'),
    path('danh-muc/sinh-ma-vach/', views.product_generate_barcodes, name='product_generate_barcodes'),
    path('danh-muc/them/', views.product_create, name='product_create'),
    path('danh-muc/dong-bo-kv/', views.product_sync_kv, name='product_sync_kv'),
    path('danh-muc/<int:pk>/', views.product_detail, name='product_detail'),
    path('danh-muc/<int:pk>/sua/', views.product_edit, name='product_edit'),
    path('danh-muc/<int:pk>/ngung/', views.product_deactivate, name='product_deactivate'),
    path('danh-muc/<int:pk>/dung-lai/', views.product_reactivate, name='product_reactivate'),
    path('danh-muc/<int:pk>/xoa/', views.product_delete, name='product_delete'),
    # Thiết lập mã
    path('thiet-lap-ma/', views_code_settings.code_settings_hub, name='code_settings_hub'),
    path('thiet-lap-ma/loai/', views_code_settings.type_list, name='type_list'),
    path('thiet-lap-ma/loai/them/', views_code_settings.type_create, name='type_create'),
    path('thiet-lap-ma/loai/<int:pk>/sua/', views_code_settings.type_edit, name='type_edit'),
    path('thiet-lap-ma/style/', views_code_settings.style_list, name='style_list'),
    path('thiet-lap-ma/style/them/', views_code_settings.style_create, name='style_create'),
    path('thiet-lap-ma/style/<int:pk>/sua/', views_code_settings.style_edit, name='style_edit'),
    path('thiet-lap-ma/map-kv/', views_code_settings.kv_map_list, name='kv_map_list'),
    path('thiet-lap-ma/map-kv/them/', views_code_settings.kv_map_create, name='kv_map_create'),
    path('thiet-lap-ma/map-kv/<int:pk>/sua/', views_code_settings.kv_map_edit, name='kv_map_edit'),
    path('thiet-lap-ma/map-kv/<int:pk>/xoa/', views_code_settings.kv_map_delete, name='kv_map_delete'),
    path('thiet-lap-ma/gan-ma/', views_code_settings.assign_codes_from_maps, name='assign_codes_from_maps'),
]
