from django.urls import path
from . import views

urlpatterns = [
    path('admin/recruitment/kanban/', views.kanban_board, name='kanban_board'),
    path('admin/recruitment/kanban/update-status/', views.update_candidate_status, name='update_candidate_status'),
    path('admin/recruitment/candidate/add/', views.add_candidate, name='add_candidate'),
    path('admin/recruitment/jobs/', views.job_posting_list, name='job_posting_list'),
    path('admin/recruitment/jobs/add/', views.job_posting_create, name='job_posting_create'),
    path('admin/recruitment/jobs/<int:pk>/edit/', views.job_posting_edit, name='job_posting_edit'),
    path('admin/recruitment/jobs/<int:pk>/delete/', views.job_posting_delete, name='job_posting_delete'),
    path('admin/recruitment/candidate/<int:candidate_id>/convert/', views.convert_to_employee, name='convert_to_employee'),
    path('admin/candidate/<int:pk>/detail/', views.candidate_detail_ajax, name='candidate_detail_ajax'),
    path('admin/recruitment/update-note/', views.update_hr_note, name='update_hr_note'),
]