from django.urls import path

from . import views

app_name = 'ra_mat_sp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('ke-hoach/', views.plan_list, name='list'),
    path('ke-hoach/tao/', views.plan_create, name='create'),
    path('ke-hoach/<int:pk>/', views.plan_detail, name='detail'),
    path('ke-hoach/<int:pk>/sua/', views.plan_edit, name='edit'),
    path('ke-hoach/<int:pk>/xoa/', views.plan_delete, name='delete'),
    path('ke-hoach/<int:pk>/thao-tac/<slug:action>/', views.plan_action, name='action'),
    path('lich/', views.calendar_view, name='calendar'),
    path('viec-cua-toi/', views.my_tasks, name='my_tasks'),
    path('tep/<int:pk>/', views.task_file, name='task_file'),
    path('cho-duyet/', views.approve_queue, name='approve_queue'),
    path('thiet-lap/', views.module_settings, name='settings'),
]
