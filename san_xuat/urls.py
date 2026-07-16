from django.urls import path

from san_xuat import views, views_hub

app_name = 'san_xuat'

urlpatterns = [
    path('', views.hub, name='hub'),
    path('tong-quan/', views_hub.overview, name='overview'),
    path('don-hang/', views_hub.redirect_orders, name='redirect_orders'),
    path('ke-hoach/', views_hub.plan_stub, name='plan_stub'),
    path('dieu-phoi/', views_hub.dispatch_stub, name='dispatch_stub'),
    path('chat-luong/', views_hub.qc_stub, name='qc_stub'),
    path('gia-thanh/', views_hub.redirect_costing, name='redirect_costing'),
    path('kho-san-pham/', views_hub.redirect_fg_stock, name='redirect_fg_stock'),
    path('kho-npl/', views_hub.redirect_npl_stock, name='redirect_npl_stock'),
    path('quy-trinh/', views_hub.process_stub, name='process_stub'),
    path('ho-so/', views.doc_list, name='doc_list'),
    path('ho-so/them/', views.doc_create, name='doc_create'),
    path('ho-so/<int:pk>/', views.doc_detail, name='doc_detail'),
    path('api/tim-ma-sp/', views.product_code_search, name='product_code_search'),
]
