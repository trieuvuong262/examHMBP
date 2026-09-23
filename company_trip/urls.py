from django.urls import path

from . import views

app_name = 'company_trip'

# Mounted at /tien-ich/dat-lich/
urlpatterns = [
    path('', views.hub, name='hub'),
    path('dang-ky/', views.register, name='register'),
    path('cam-on/', views.thank_you, name='thank_you'),
    path('api/companion-search/', views.companion_search, name='companion_search'),
    path('quan-ly/dang-ky/', views.manage_list, name='manage_list'),
    path('quan-ly/dang-ky/xuat/', views.manage_export, name='manage_export'),
    path('quan-ly/dang-ky/<int:pk>/huy/', views.manage_cancel, name='manage_cancel'),
    path('quan-ly/email/', views.email_manage, name='email'),
]
