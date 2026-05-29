from django.urls import path

from . import views

app_name = 'service_requests'

urlpatterns = [
    path('', views.request_hub, name='hub'),
    path('cua-toi/', views.my_requests, name='my'),
    path('cho-xu-ly/', views.pending_requests, name='pending'),
    path('tao/', views.create_request, name='create'),
    path('<int:pk>/', views.request_detail, name='detail'),
]
