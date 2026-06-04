from django.urls import path

from . import lookup_views, views

app_name = 'kiotviet'

urlpatterns = [
    path('khach-hang/', views.customer_lookup, name='customer_lookup'),
    path('khach-hang/<int:customer_id>/', views.customer_detail, name='customer_detail'),
    path('don-dat-hang/', lookup_views.order_lookup, name='order_lookup'),
    path('don-dat-hang/<int:order_id>/', lookup_views.order_detail, name='order_detail'),
    path('hoa-don/', lookup_views.invoice_lookup, name='invoice_lookup'),
    path('hoa-don/<int:invoice_id>/', lookup_views.invoice_detail, name='invoice_detail'),
]
