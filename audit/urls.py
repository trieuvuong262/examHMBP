from django.urls import path

from . import views

app_name = 'audit'

urlpatterns = [
    path('', views.log_list, name='log_list'),
    path('backup/', views.backup_page, name='backup_page'),
    path('backup/run/', views.backup_run, name='backup_run'),
    path('nas-links/', views.nas_links_index, name='nas_links'),
    path('<int:pk>/', views.log_detail, name='log_detail'),
    path('user/<int:user_id>/', views.user_timeline, name='user_timeline'),
]
