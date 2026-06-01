from django.urls import path

from . import views

app_name = 'feedback'

urlpatterns = [
    path('', views.feedback_hub, name='hub'),
    path('cua-toi/', views.my_list, name='my_list'),
    path('tao/', views.create, name='create'),
    path('cho-xu-ly/', views.review_list, name='review_list'),
    path('<int:pk>/', views.detail, name='detail'),
]
