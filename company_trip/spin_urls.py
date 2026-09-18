from django.urls import path

from . import views

app_name = 'company_trip_spin'

# Mounted at /tien-ich/vong-quay/
urlpatterns = [
    path('', views.spin_page, name='spin'),
    path('spin/', views.spin_api, name='spin_result'),
    path('api/check_lucky/', views.check_lucky, name='check_lucky'),
    path('api/spin/', views.spin_api, name='spin_api'),
    path('api/spin/seed/', views.spin_seed, name='spin_seed'),
]
