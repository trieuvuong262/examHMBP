from django.urls import path

from kho_san_pham import views

app_name = 'kho_san_pham'

urlpatterns = [
    path('', views.hub_redirect, name='hub'),
    path('danh-muc/', views.product_list, name='product_list'),
    path('danh-muc/xuat-excel/', views.product_export, name='product_export'),
    path('danh-muc/mau-excel/', views.product_import_template, name='product_import_template'),
    path('danh-muc/nhap-excel/', views.product_import, name='product_import'),
    path('danh-muc/them/', views.product_create, name='product_create'),
    path('danh-muc/dong-bo-kv/', views.product_sync_kv, name='product_sync_kv'),
    path('danh-muc/<int:pk>/', views.product_detail, name='product_detail'),
    path('danh-muc/<int:pk>/sua/', views.product_edit, name='product_edit'),
    path('danh-muc/<int:pk>/ngung/', views.product_deactivate, name='product_deactivate'),
    path('danh-muc/<int:pk>/xoa/', views.product_delete, name='product_delete'),
]
