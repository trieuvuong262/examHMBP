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
    path('admin/recruitment/set-interview/', views.set_interview_schedule, name='set_interview_schedule'),
    path('admin/recruitment/interviews/all/', views.get_all_interviews, name='get_all_interviews'),
    path('admin/recruitment/candidate/<int:pk>/interview/', views.get_candidate_interview, name='get_candidate_interview'),
    path('admin/recruitment/candidate/update-license/', views.update_practice_license, name='update_practice_license'),
    path('admin/recruitment/candidate/<int:pk>/license/', views.get_candidate_license, name='get_candidate_license'),
    path('admin/recruitment/licenses/all/', views.get_all_licenses, name='get_all_licenses'),
    path('admin/recruitment/interviews/export/', views.export_interviews_excel, name='export_interviews_excel'),
    path('admin/recruitment/licenses/export/', views.export_licenses_excel, name='export_licenses_excel'),
]