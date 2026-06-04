from django.urls import path

from . import views

app_name = 'kiotviet'

urlpatterns = [
    path('khach-hang/', views.customer_lookup, name='customer_lookup'),
    path('khach-hang/<int:customer_id>/', views.customer_detail, name='customer_detail'),
]
