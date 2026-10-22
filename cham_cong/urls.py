from django.urls import path

from cham_cong import views, views_leave, views_payroll, views_setup, views_timesheet

app_name = 'cham_cong'

urlpatterns = [
    path('', views.punch, name='punch'),
    path('lich-su/', views.history, name='history'),
    path('don-bo-sung/', views.supplement_list, name='supplements'),
    path('don-bo-sung/tao/', views.supplement_create, name='supplement_create'),
    path('don-bo-sung/<int:pk>/duyet/', views.supplement_decide, name='supplement_decide'),
    path('bang-cong/', views_timesheet.timesheet, name='timesheet'),
    path('bang-cong/chinh-sua/', views_timesheet.adjustment_create, name='adjustment_create'),
    path('bang-cong/dieu-chinh/<int:pk>/duyet/', views_timesheet.adjustment_decide, name='adjustment_decide'),
    path('bang-cong/khoa/', views_timesheet.timesheet_lock, name='timesheet_lock'),
    path('nghi-phep/', views_leave.leave_list, name='leaves'),
    path('nghi-phep/tao/', views_leave.leave_create, name='leave_create'),
    path('nghi-phep/<int:pk>/duyet/', views_leave.leave_decide, name='leave_decide'),
    path('nghi-phep/<int:pk>/huy/', views_leave.leave_cancel, name='leave_cancel'),
    path('ca/', views_setup.schedule, name='schedule'),
    path('ca/moi/', views_setup.shift_edit, name='shift_create'),
    path('ca/<int:pk>/sua/', views_setup.shift_edit, name='shift_edit'),
    path('ca/gan/', views_setup.assignment_save, name='assignment_save'),
    path('ca/gan/<int:pk>/go/', views_setup.assignment_off, name='assignment_off'),
    path('ca/ngay-le/', views_setup.holiday_save, name='holiday_save'),
    path('ca/ngay-le/<int:pk>/xoa/', views_setup.holiday_delete, name='holiday_delete'),
    path('dia-diem/', views_setup.site_list, name='sites'),
    path('dia-diem/moi/', views_setup.site_edit, name='site_create'),
    path('dia-diem/<int:pk>/sua/', views_setup.site_edit, name='site_edit'),
    path('cau-hinh/', views_setup.hr_config, name='hr_config'),
    path('cau-hinh/luu/', views_setup.policy_save, name='policy_save'),
    path('bao-cao/', views_setup.hr_report, name='hr_report'),
    path('nhat-ky/', views_setup.hr_log, name='hr_log'),
    path('bang-luong/', views_payroll.payroll, name='payroll'),
    path('bang-luong/tinh/', views_payroll.payroll_calculate, name='payroll_calculate'),
    path('bang-luong/chot/', views_payroll.payroll_close, name='payroll_close'),
    path('bang-luong/muc-luong/', views_payroll.salary_list, name='salary_list'),
    path('bang-luong/muc-luong/<int:user_id>/', views_payroll.salary_edit, name='salary_edit'),
    path('bang-luong/thuong/', views_payroll.pay_adjustment_create, name='payroll_bonus'),
    path('bang-luong/thuong/<int:pk>/duyet/', views_payroll.pay_adjustment_decide, name='payroll_bonus_decide'),
    path('bang-luong/<int:user_id>/', views_payroll.payroll_slip, name='payroll_slip'),
]
