from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_hub, name='hub'),
    path('today/', views.today_report, name='today'),
    path('weekly/', views.weekly_report, name='weekly'),
    path('copy-prev-week/', views.copy_prev_week, name='copy_prev_week'),
    path('ckeditor5-upload/', views.ckeditor5_upload, name='ckeditor5_upload'),
    path('copy-yesterday/', views.copy_yesterday, name='copy_yesterday'),
    path('my/', views.my_reports, name='my'),
    path('team/', views.team_reports, name='team'),
    path('team/weekly/', views.team_weekly_reports, name='team_weekly'),
    path('weekly/<int:pk>/', views.weekly_report_detail, name='weekly_detail'),
    path('<int:pk>/', views.report_detail, name='detail'),
]
