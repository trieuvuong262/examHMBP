from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'service_requests'

urlpatterns = [
    path('', views.request_hub, name='hub'),

    # Đề xuất mới (mua hàng / đề xuất)
    path('de-xuat/cua-toi/', views.my_requests, {'flow_tab': 'de_xuat'}, name='de_xuat_my'),
    path('de-xuat/cho-xu-ly/', views.pending_requests, {'flow_tab': 'de_xuat'}, name='de_xuat_pending'),
    path('de-xuat/theo-doi/', views.involved_requests, {'flow_tab': 'de_xuat'}, name='de_xuat_involved'),
    path('de-xuat/tao/', views.create_request, name='create'),
    path('de-xuat/danh-muc-dinh-ky/', views.recurring_catalog_list, name='catalog_list'),
    path('de-xuat/danh-muc-dinh-ky/them/', views.recurring_catalog_create, name='catalog_create'),
    path('de-xuat/danh-muc-dinh-ky/<int:pk>/sua/', views.recurring_catalog_edit, name='catalog_edit'),
    path('de-xuat/danh-muc-dinh-ky/<int:pk>/an/', views.recurring_catalog_delete, name='catalog_delete'),

    # Hỗ trợ kỹ thuật (sửa chữa thiết bị)
    path(
        'ho-tro/',
        RedirectView.as_view(pattern_name='service_requests:ho_tro_my', permanent=False),
        name='ho_tro_hub',
    ),
    path('ho-tro/cua-toi/', views.my_requests, {'flow_tab': 'ho_tro'}, name='ho_tro_my'),
    path('ho-tro/cho-xu-ly/', views.pending_requests, {'flow_tab': 'ho_tro'}, name='ho_tro_pending'),
    path('ho-tro/theo-doi/', views.involved_requests, {'flow_tab': 'ho_tro'}, name='ho_tro_involved'),
    path('ho-tro/tao/', views.create_it_repair, name='create_it_repair'),
    path(
        'ho-tro/tao/it/',
        RedirectView.as_view(pattern_name='service_requests:create_it_repair', query_string='tab=it', permanent=False),
        name='create_it_repair_it',
    ),
    path(
        'ho-tro/tao/san-xuat/',
        RedirectView.as_view(
            pattern_name='service_requests:create_it_repair',
            query_string='tab=production',
            permanent=False,
        ),
        name='create_it_repair_production',
    ),

    path('de-xuat/<int:pk>/', views.request_detail, {'flow_tab': 'de_xuat'}, name='de_xuat_detail'),
    path('ho-tro/<int:pk>/', views.request_detail, {'flow_tab': 'ho_tro'}, name='ho_tro_detail'),
    path('<int:pk>/', views.request_detail_legacy, name='detail'),

    # Alias cũ — chuyển hướng
    path('cua-toi/', views.my_requests, {'flow_tab': 'de_xuat'}, name='my'),
    path('cho-xu-ly/', views.pending_requests, {'flow_tab': 'de_xuat'}, name='pending'),
    path('tao/', RedirectView.as_view(pattern_name='service_requests:create', permanent=False)),
    path('sua-it/tao/', RedirectView.as_view(pattern_name='service_requests:create_it_repair', permanent=False)),
    path('danh-muc-dinh-ky/', RedirectView.as_view(pattern_name='service_requests:catalog_list', permanent=False)),
    path('danh-muc-dinh-ky/them/', RedirectView.as_view(pattern_name='service_requests:catalog_create', permanent=False)),
    path(
        'danh-muc-dinh-ky/<int:pk>/sua/',
        RedirectView.as_view(pattern_name='service_requests:catalog_edit', permanent=False),
    ),
    path(
        'danh-muc-dinh-ky/<int:pk>/an/',
        RedirectView.as_view(pattern_name='service_requests:catalog_delete', permanent=False),
    ),
]
