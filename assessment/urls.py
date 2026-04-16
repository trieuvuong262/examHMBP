from django.urls import path
from . import views

urlpatterns = [
    # --- Dành cho nhân viên ---
     path('', views.home_portal, name='home_portal'), # Trang chủ bây giờ là Portal
     path('exams/', views.exam_list, name='exam_list'), # Trang thi dời vào đường dẫn /exams/
     path('exams/<int:exam_id>/take/', views.take_exam, name='take_exam'),
    
    # --- Dành cho Admin (Dashboard & Kỳ thi) ---
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/exam/add/', views.exam_create, name='exam_create'),
    path('dashboard/exam/<int:pk>/edit/', views.exam_edit, name='exam_edit'),
    path('dashboard/exam/<int:pk>/delete/', views.exam_delete, name='exam_delete'),
    
    # --- Quản lý câu hỏi (Gắn với một kỳ thi cụ thể) ---
    # Thêm mới
    path('dashboard/exam/<int:exam_id>/question/add/', 
         views.question_add, name='question_add'),
    
    # Sửa câu hỏi đã có
    path('dashboard/exam/<int:exam_id>/question/<int:question_id>/edit/', 
         views.question_edit, name='question_edit_detail'),
    
    # Gỡ câu hỏi khỏi bài thi
    path('dashboard/exam/<int:exam_id>/question/<int:question_id>/remove/', 
         views.question_remove, name='question_remove'),
    
    # --- Kết quả và chấm điểm ---
    path('dashboard/results/', views.admin_results, name='admin_results'),
    
    # Dòng hiện tại của bạn
    path('dashboard/submission/<int:submission_id>/grade/', 
         views.grade_submission, name='grade_submission'),
    
    
    path('dashboard/users/', views.user_list, name='user_list'),
    path('dashboard/users/add/', views.user_add, name='user_add'),
    path('dashboard/users/edit/<int:user_id>/', views.user_edit, name='user_edit'),
    path('dashboard/users/delete/<int:user_id>/', views.user_delete, name='user_delete'),
    path('dashboard/users/<int:user_id>/reset-password/', views.user_password_reset, name='user_password_reset'),
    
    path('dashboard/competency/add-ajax/', views.competency_add_ajax, name='competency_add_ajax'),
    path('dashboard/competency/delete/<int:pk>/', views.competency_delete_ajax, name='competency_delete_ajax'),
    
    path('dashboard/users/import/', views.user_import_excel, name='user_import_excel'),
    path('dashboard/users/export/', views.user_export_excel, name='user_export_excel'),
     path('dashboard/users/download-template/', views.user_download_template, name='user_download_template'),
]