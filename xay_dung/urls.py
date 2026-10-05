from django.urls import path

from . import views

app_name = 'xay_dung'

urlpatterns = [
    path('', views.model_list, name='list'),
    path('tao/', views.model_create, name='create'),
    path('<int:pk>/', views.model_detail, name='detail'),
    path('<int:pk>/sua/', views.model_update, name='update'),
    path('<int:pk>/xoa/', views.model_delete, name='delete'),
    path('<int:pk>/xem/', views.model_raw, name='raw'),
]
