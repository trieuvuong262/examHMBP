from django.urls import path

from . import ksk_views, views

app_name = 'surveys'

urlpatterns = [
    path('', views.survey_hub, name='hub'),
    path('quan-ly/tao/', views.survey_create, name='create'),
    path('quan-ly/', views.survey_manage_list, name='manage_list'),
    path('quan-ly/<int:pk>/link/', views.survey_reference_edit, name='reference_edit'),
    path('quan-ly/<int:pk>/link-gui/', views.survey_share_detail, name='share_detail'),
    path('cap-nhat-thong-tin/', ksk_views.health_check_update, name='ksk_update'),
    path('quan-ly-ksk/', ksk_views.health_check_results, name='ksk_results'),
    path('quan-ly-ksk/xuat-excel/', ksk_views.health_check_export, name='ksk_export'),
    path('quan-ly-ksk/thoi-gian/', ksk_views.health_check_schedule, name='ksk_schedule'),
    path('quan-ly-ksk/ma-nv/<int:pk>/', ksk_views.health_check_set_code, name='ksk_set_code'),
    path('ket-qua/', views.survey_results, name='results'),
    path('ket-qua/<int:pk>/', views.survey_result_detail, name='result_detail'),
    path('ket-qua/<int:pk>/xuat-excel/', views.survey_result_export, name='result_export'),
    path('d/<uuid:token>/', views.survey_fill, name='fill'),
]
