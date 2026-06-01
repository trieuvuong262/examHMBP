from django.urls import path

from . import cross_dept_views, project_views, views

app_name = 'tasks'

urlpatterns = [
    path('', views.task_hub, name='hub'),
    path('ca-nhan/', views.personal_hub, name='personal_hub'),
    path('ca-nhan/cua-toi/', views.my_tasks, name='my'),
    path('ca-nhan/da-giao/', views.assigned_tasks, name='assigned'),
    path('ca-nhan/giao/', views.assign_task, name='assign'),
    path('ca-nhan/lap-lai/', views.recurring_tasks, name='recurring'),
    path('ca-nhan/lap-lai/<int:pk>/', views.recurrence_action, name='recurrence_action'),
    path('ca-nhan/<int:pk>/', views.task_detail, name='detail'),
    path('ca-nhan/<int:pk>/giao-lai/', views.reassign_task, name='reassign'),
    path('du-an/', project_views.project_list, name='project_list'),
    path('du-an/tao/', project_views.project_create, name='project_create'),
    path('du-an/<int:pk>/', project_views.project_detail, name='project_detail'),
    path('du-an/viec/<int:pk>/', views.task_detail, name='project_step'),
    path('du-an/viec/<int:pk>/chuyen-giao/', project_views.request_handoff, name='handoff'),
    path('du-an/viec/<int:pk>/giao-lai/', project_views.reassign_project_step, name='project_reassign'),
    path('lien-phong-ban/', cross_dept_views.cross_dept_list, name='cross_dept_list'),
    path('lien-phong-ban/tao/', cross_dept_views.cross_dept_create, name='cross_dept_create'),
    path('lien-phong-ban/cho-tiep-nhan/', cross_dept_views.cross_dept_pending, name='cross_dept_pending'),
    path('lien-phong-ban/<int:pk>/', cross_dept_views.cross_dept_detail, name='cross_dept_detail'),
    path('lien-phong-ban/viec/<int:pk>/', views.task_detail, name='cross_dept_step'),
    path('lien-phong-ban/viec/<int:pk>/tiep-nhan/', cross_dept_views.claim_cross_dept_step, name='cross_dept_claim'),
    path('lien-phong-ban/viec/<int:pk>/chuyen-giao/', project_views.request_handoff, name='cross_dept_handoff'),
    path('lien-phong-ban/viec/<int:pk>/giao-lai/', project_views.reassign_project_step, name='cross_dept_reassign'),
]
