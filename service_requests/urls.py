from django.urls import path

from . import views

app_name = 'service_requests'

urlpatterns = [
    path('', views.request_hub, name='hub'),
    path('cua-toi/', views.my_requests, name='my'),
    path('cho-xu-ly/', views.pending_requests, name='pending'),
    path('tao/', views.create_request, name='create'),
    path('danh-muc-dinh-ky/', views.recurring_catalog_list, name='catalog_list'),
    path('danh-muc-dinh-ky/them/', views.recurring_catalog_create, name='catalog_create'),
    path('danh-muc-dinh-ky/<int:pk>/sua/', views.recurring_catalog_edit, name='catalog_edit'),
    path('danh-muc-dinh-ky/<int:pk>/an/', views.recurring_catalog_delete, name='catalog_delete'),
    path('<int:pk>/', views.request_detail, name='detail'),
]
