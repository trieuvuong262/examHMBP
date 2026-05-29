from django.urls import path

from . import project_views, views

app_name = 'tasks'

urlpatterns = [
    path('', views.task_hub, name='hub'),
    path('ca-nhan/', views.personal_hub, name='personal_hub'),
    path('ca-nhan/cua-toi/', views.my_tasks, name='my'),
    path('ca-nhan/da-giao/', views.assigned_tasks, name='assigned'),
    path('ca-nhan/giao/', views.assign_task, name='assign'),
    path('ca-nhan/<int:pk>/', views.task_detail, name='detail'),
    path('ca-nhan/<int:pk>/giao-lai/', views.reassign_task, name='reassign'),
    path('du-an/', project_views.project_list, name='project_list'),
    path('du-an/tao/', project_views.project_create, name='project_create'),
    path('du-an/<int:pk>/', project_views.project_detail, name='project_detail'),
    path('du-an/viec/<int:pk>/', views.task_detail, name='project_step'),
    path('du-an/viec/<int:pk>/chuyen-giao/', project_views.request_handoff, name='handoff'),
    path('du-an/viec/<int:pk>/giao-lai/', project_views.reassign_project_step, name='project_reassign'),
]
