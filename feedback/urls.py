from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'feedback'

urlpatterns = [
    path('', views.feedback_hub, name='hub'),
    path('tao/', views.create, name='create'),
    path('danh-sach/', views.feedback_list, name='list'),
    path('<int:pk>/', views.detail, name='detail'),
    path('cua-toi/', RedirectView.as_view(pattern_name='feedback:create', permanent=False)),
    path('cho-xu-ly/', RedirectView.as_view(pattern_name='feedback:list', permanent=False)),
]
