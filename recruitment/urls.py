from django.urls import path

from . import views

urlpatterns = [
    path('', views.recruitment_overview, name='recruitment_overview'),
    # Vị trí tuyển dụng (menu «jobs»)
    path('admin/recruitment/jobs/', views.job_posting_list, name='job_posting_list'),
    path('admin/recruitment/jobs/add/', views.job_posting_create, name='job_posting_create'),
    path('admin/recruitment/jobs/<int:pk>/edit/', views.job_posting_edit, name='job_posting_edit'),
    path('admin/recruitment/jobs/<int:pk>/status/', views.job_posting_status, name='job_posting_status'),
    path('admin/recruitment/jobs/<int:pk>/delete/', views.job_posting_delete, name='job_posting_delete'),
    # Thiết lập danh mục (menu «settings»)
    path('admin/recruitment/settings/', views.recruitment_settings, name='recruitment_settings'),
    path('admin/recruitment/settings/<slug:tab>/add/', views.recruitment_settings_add, name='recruitment_settings_add'),
    path('admin/recruitment/settings/<slug:tab>/<int:pk>/edit/', views.recruitment_settings_edit, name='recruitment_settings_edit'),
    path('admin/recruitment/settings/<slug:tab>/<int:pk>/toggle/', views.recruitment_settings_toggle, name='recruitment_settings_toggle'),
    path('admin/recruitment/settings/<slug:tab>/<int:pk>/delete/', views.recruitment_settings_delete, name='recruitment_settings_delete'),
    # Ứng viên (menu «candidates»)
    path('admin/recruitment/candidates/', views.candidate_list, name='candidate_list'),
    path('admin/recruitment/candidates/export/', views.export_candidates_excel, name='export_candidates_excel'),
    path('admin/recruitment/kanban/', views.kanban_board, name='kanban_board'),
    path('admin/recruitment/candidate/add/', views.add_candidate, name='add_candidate'),
    path('admin/recruitment/candidate/<int:pk>/', views.candidate_detail, name='candidate_detail'),
    path('admin/recruitment/candidate/<int:pk>/transition/', views.candidate_transition, name='candidate_transition'),
    path('admin/recruitment/candidate/<int:pk>/interview-result/', views.candidate_interview_result, name='candidate_interview_result'),
    path('admin/recruitment/candidate/<int:pk>/onboard/', views.candidate_onboard, name='candidate_onboard'),
    path('admin/recruitment/candidate/<int:pk>/files/', views.candidate_file_upload, name='candidate_file_upload'),
    path('admin/recruitment/candidate/<int:pk>/files/<int:file_pk>/delete/', views.candidate_file_delete, name='candidate_file_delete'),
    # File hồ sơ — view tự kiểm tra quyền (HR / quản lý đúng phòng / người phỏng vấn)
    path('ho-so-ung-vien/<int:pk>/', views.candidate_file, name='recruitment_file'),
    path('admin/recruitment/interviews/', views.interview_list, name='interview_list'),
    path('admin/recruitment/interviews/export/', views.export_interviews_excel, name='export_interviews_excel'),
    # Trưởng bộ phận / Trưởng phòng / Giám đốc — view tự kiểm tra vai trò
    path('danh-gia-ung-vien/', views.review_list, name='recruitment_review_list'),
    path('danh-gia-ung-vien/de-xuat/', views.refer_candidate, name='recruitment_refer_candidate'),
    path('danh-gia-ung-vien/goi-y-email/', views.candidate_suggest_email, name='recruitment_suggest_email'),
    path('danh-gia-ung-vien/<int:pk>/', views.review_candidate, name='recruitment_review_candidate'),
    path('danh-gia-ung-vien/<int:pk>/ket-qua-pv/', views.review_interview_result, name='recruitment_review_interview_result'),
    path('danh-gia-ung-vien/<int:pk>/files/', views.manager_file_upload, name='recruitment_manager_file_upload'),
]
