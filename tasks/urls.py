from django.urls import path

from . import project_views, views

app_name = 'tasks'

urlpatterns = [
    path('', views.task_hub, name='hub'),
    path('cua-toi/', views.my_tasks, name='my'),
    path('da-giao/', views.assigned_tasks, name='assigned'),
    path('giao/', views.assign_task, name='assign'),
    path('du-an/', project_views.project_list, name='project_list'),
    path('du-an/tao/', project_views.project_create, name='project_create'),
    path('du-an/<int:pk>/', project_views.project_detail, name='project_detail'),
    path('<int:pk>/chuyen-giao/', project_views.request_handoff, name='handoff'),
    path('<int:pk>/', views.task_detail, name='detail'),
    path('<int:pk>/giao-lai/', views.reassign_task, name='reassign'),
]
