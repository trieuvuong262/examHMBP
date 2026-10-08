from django.urls import path

from . import views

app_name = 'thiet_ke_sp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('ho-so/', views.dossier_list, name='list'),
    path('kanban/', views.kanban, name='kanban'),
    path('kanban/<int:pk>/chuyen/', views.kanban_move, name='kanban_move'),
    path('bao-cao/', views.report, name='reports'),
    path('ho-so/tao/', views.dossier_create, name='create'),
    path('ho-so/<int:pk>/', views.dossier_detail, name='detail'),
    path('ho-so/<int:pk>/sua/', views.dossier_edit, name='edit'),
    path('ho-so/<int:pk>/xoa/', views.dossier_delete, name='delete'),
    path('ho-so/<int:pk>/thao-tac/<slug:action>/', views.dossier_action, name='action'),
    path('ho-so/<int:pk>/tai-tep/', views.attachment_upload, name='upload'),
    path('tep/<int:att_pk>/', views.attachment_serve, name='attachment_serve'),
    path('tep/<int:att_pk>/xoa/', views.attachment_delete, name='attachment_delete'),
    path('cho-toi/', views.my_tasks, name='my_tasks'),
    path('duyet/', views.approve_queue, name='approve_queue'),
    path('thong-bao/', views.notifications, name='notifications'),
    path('thong-bao/<int:pk>/', views.notification_open, name='notification_open'),
    path('thiet-lap/', views.module_settings, name='settings'),
]
