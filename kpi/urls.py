from django.urls import path

from . import views

urlpatterns = [
    path('', views.kpi_list_view, name='kpi_list'),
    path('tong-ket/', views.kpi_summary_view, name='kpi_summary'),
    path('detail/<int:kpi_id>/', views.kpi_detail_view, name='kpi_detail'),
    path('detail/<int:kpi_id>/upload-image/', views.kpi_inline_upload, name='kpi_inline_upload'),
    path('detail/<int:kpi_id>/delete/', views.kpi_delete_view, name='kpi_delete'),
    path('inline-image/<path:relpath>', views.kpi_inline_image_serve, name='kpi_inline_image'),
    path('import-excel/', views.kpi_import_excel, name='kpi_import_excel'),
    path('import-excel/sample/', views.download_kpi_sample_excel, name='download_kpi_sample_excel'),
]
