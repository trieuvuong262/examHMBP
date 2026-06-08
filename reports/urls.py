from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_hub, name='hub'),
    path('today/', views.today_report, name='today'),
    path('ckeditor5-upload/', views.ckeditor5_upload, name='ckeditor5_upload'),
    path('copy-yesterday/', views.copy_yesterday, name='copy_yesterday'),
    path('my/', views.my_reports, name='my'),
    path('team/', views.team_reports, name='team'),
    path('<int:pk>/', views.report_detail, name='detail'),
]
