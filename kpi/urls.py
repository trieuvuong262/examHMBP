from django.urls import path
from . import views

urlpatterns = [
    # 1. Trang Dashboard chính (Hiển thị các bảng KPI năm)
    path('', views.kpi_list_view, name='kpi_list'),
    
    # 2. Trang Chi tiết & Chấm điểm (All-in-one Form cho Q1, Q2, Q3, Q4)
    # Lưu ý: kpi_id ở đây chính là ID của YearlyKpi
    path('detail/<int:kpi_id>/', views.kpi_detail_view, name='kpi_detail'),
    
    # 3. Chức năng Giao KPI Năm (Thiết lập tay)
    path('yearly/create/', views.yearly_kpi_create, name='yearly_kpi_create'),
    
    # 4. Chức năng Import & Export Excel
    path('import-excel/', views.kpi_import_excel, name='kpi_import_excel'),
    path('import-excel/sample/', views.download_kpi_sample_excel, name='download_kpi_sample_excel'),    

]