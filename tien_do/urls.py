from django.urls import path

from . import views

app_name = 'tien_do'

urlpatterns = [
    path('', views.board_portal, name='portal'),
    path('portal/', views.board_portal, name='portal_alt'),
    path('website-si-le/', views.board_wholesale_retail, name='wholesale_retail'),
    path('website-si-le/xuat-excel/', views.board_wholesale_retail_export, name='wholesale_retail_export'),
    path('them/<str:platform>/', views.item_create, name='item_create'),
    path('import/mau/', views.import_template, name='import_template'),
    path('import/<str:platform>/', views.item_import, name='item_import'),
    path('tai-anh/', views.item_image_upload, name='item_image_upload'),
    path('anh/<path:relpath>', views.item_image_serve, name='item_image'),
    path('<int:pk>/sua-o/', views.item_cell_update, name='item_cell_update'),
    path('<int:pk>/feedback/', views.item_feedback_create, name='item_feedback_create'),
    path('<int:pk>/xoa/', views.item_delete, name='item_delete'),
]
