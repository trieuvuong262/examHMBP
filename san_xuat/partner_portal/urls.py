"""URLconf riêng cho host pn.justplay.vn — không có đường dẫn nào tới portal nội bộ."""

from django.urls import path

from san_xuat.partner_portal import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dang-nhap/', views.login_view, name='login'),
    path('dang-xuat/', views.logout_view, name='logout'),
    path('doi-mat-khau/', views.change_password, name='change_password'),
    path('don/<int:pk>/', views.order_detail, name='order_detail'),
    path('bao-cao/', views.reports, name='reports'),
]
