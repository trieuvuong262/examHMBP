from django.urls import path

from . import views

app_name = 'surveys'

urlpatterns = [
    path('', views.survey_hub, name='hub'),
    path('quan-ly/tao/', views.survey_create, name='create'),
    path('quan-ly/', views.survey_manage_list, name='manage_list'),
    path('quan-ly/<int:pk>/link/', views.survey_reference_edit, name='reference_edit'),
    path('quan-ly/<int:pk>/link-gui/', views.survey_share_detail, name='share_detail'),
    path('ket-qua/', views.survey_results, name='results'),
    path('ket-qua/<int:pk>/', views.survey_result_detail, name='result_detail'),
    path('d/<uuid:token>/', views.survey_fill, name='fill'),
]
