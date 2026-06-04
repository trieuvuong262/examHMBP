from django.urls import path

from . import catalog_views, lookup_views, views

app_name = 'kiotviet'

urlpatterns = [
    path('khach-hang/', views.customer_lookup, name='customer_lookup'),
    path('khach-hang/<int:customer_id>/', views.customer_detail, name='customer_detail'),
    path('don-dat-hang/', lookup_views.order_lookup, name='order_lookup'),
    path('don-dat-hang/<int:order_id>/', lookup_views.order_detail, name='order_detail'),
    path('hoa-don/', lookup_views.invoice_lookup, name='invoice_lookup'),
    path('hoa-don/<int:invoice_id>/', lookup_views.invoice_detail, name='invoice_detail'),
    path('hang-hoa/', catalog_views.product_lookup, name='product_lookup'),
    path('hang-hoa/<int:product_id>/', catalog_views.product_detail, name='product_detail'),
    path('ton-kho/', catalog_views.stock_lookup, name='stock_lookup'),
    path('phieu-nhap/', catalog_views.purchase_lookup, name='purchase_lookup'),
    path('phieu-nhap/<int:purchase_id>/', catalog_views.purchase_detail, name='purchase_detail'),
]
