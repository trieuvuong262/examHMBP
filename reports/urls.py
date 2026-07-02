from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_hub, name='hub'),
    # Báo cáo ngày — SX (sản xuất)
    path('sx/today/', views.today_report_cn, name='today_cn'),
    path('sx/nhap-ho/', views.proxy_report_entry, name='proxy_cn'),
    path('sx/team/', views.team_reports_cn, name='team_cn'),
    path('sx/my/', views.my_reports_cn, name='my_cn'),
    path('sx/copy-yesterday/', views.copy_yesterday_cn, name='copy_yesterday_cn'),
    path('sx/<int:pk>/export/', views.report_detail_export_cn, name='detail_export_cn'),
    path('sx/<int:pk>/', views.report_detail_cn, name='detail_cn'),
    # Legacy /reports/cn/ → /reports/sx/
    path('cn/today/', views.redirect_legacy_cn_today),
    path('cn/team/', views.redirect_legacy_cn_team),
    path('cn/my/', views.redirect_legacy_cn_my),
    path('cn/copy-yesterday/', views.redirect_legacy_cn_copy_yesterday),
    path('cn/<int:pk>/export/', views.redirect_legacy_cn_export),
    path('cn/<int:pk>/', views.redirect_legacy_cn_detail),
    # Báo cáo ngày — VP (văn phòng)
    path('vp/today/', views.today_report_vp, name='today_vp'),
    path('vp/team/', views.team_reports_vp, name='team_vp'),
    path('vp/my/', views.my_reports_vp, name='my_vp'),
    path('vp/copy-yesterday/', views.copy_yesterday_vp, name='copy_yesterday_vp'),
    path('vp/copy-prev/', views.copy_prev_vp, name='copy_prev_vp'),
    path('vp/ckeditor5-upload/', views.ckeditor5_upload, name='ckeditor5_upload'),
    path('vp/<int:pk>/export/', views.report_detail_export_vp, name='detail_export_vp'),
    path('vp/<int:pk>/', views.report_detail_vp, name='detail_vp'),
    path('vp/file/<int:pk>/', views.daily_attachment_serve, name='daily_attachment'),
    path('vp/file/<int:pk>/preview/', views.daily_attachment_preview, name='daily_attachment_preview'),
    path('doc-image/<int:report_pk>/<path:relpath>', views.document_image_serve, name='document_image'),
    path('inline-image/<path:relpath>', views.inline_image_serve, name='inline_image'),
    # Báo cáo tuần — SX
    path('sx/weekly/', views.weekly_report_cn, name='weekly_cn'),
    path('sx/copy-prev-week/', views.copy_prev_week_cn, name='copy_prev_week_cn'),
    path('sx/team/weekly/', views.team_weekly_reports_cn, name='team_weekly_cn'),
    path('sx/weekly/<int:pk>/', views.weekly_report_detail_cn, name='weekly_detail_cn'),
    # Báo cáo tuần — VP
    path('vp/weekly/', views.weekly_report_vp, name='weekly_vp'),
    path('vp/copy-prev-week/', views.copy_prev_week_vp, name='copy_prev_week_vp'),
    path('vp/team/weekly/', views.team_weekly_reports_vp, name='team_weekly_vp'),
    path('vp/weekly/<int:pk>/', views.weekly_report_detail_vp, name='weekly_detail_vp'),
    # Legacy báo cáo tuần
    path('weekly/', views.weekly_report_redirect, name='weekly'),
    path('copy-prev-week/', views.copy_prev_week_redirect, name='copy_prev_week'),
    path('team/weekly/', views.team_weekly_reports_redirect, name='team_weekly'),
    path('weekly/<int:pk>/', views.weekly_report_detail_redirect, name='weekly_detail'),
    path('weekly/file/<int:pk>/', views.weekly_attachment_serve, name='weekly_attachment'),
    path('weekly/file/<int:pk>/preview/', views.weekly_attachment_preview, name='weekly_attachment_preview'),
    # Legacy — chuyển hướng sang SX/VP
    path('today/', views.today_report, name='today'),
    path('team/', views.team_reports, name='team'),
    path('my/', views.my_reports, name='my'),
    path('copy-yesterday/', views.copy_yesterday_redirect, name='copy_yesterday'),
    path('ckeditor5-upload/', views.ckeditor5_upload, name='ckeditor5_upload_legacy'),
    path('<int:pk>/export/', views.report_detail_export, name='detail_export'),
    path('<int:pk>/', views.report_detail, name='detail'),
]
