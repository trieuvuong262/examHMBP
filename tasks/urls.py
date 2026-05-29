from django.urls import path

from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.task_hub, name='hub'),
    path('cua-toi/', views.my_tasks, name='my'),
    path('da-giao/', views.assigned_tasks, name='assigned'),
    path('giao/', views.assign_task, name='assign'),
    path('<int:pk>/', views.task_detail, name='detail'),
    path('<int:pk>/giao-lai/', views.reassign_task, name='reassign'),
]
