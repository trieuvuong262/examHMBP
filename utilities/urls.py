from django.urls import path

from utilities import views

app_name = 'utilities'

urlpatterns = [
    path('', views.utilities_hub, name='hub'),
    # Đặt cơm
    path('dat-com/', views.meal_home, name='meal_home'),
    path('dat-com/mon/', views.meal_dish_list, name='meal_dish_list'),
    path('dat-com/mon/them/', views.meal_dish_create, name='meal_dish_create'),
    path('dat-com/mon/<int:pk>/sua/', views.meal_dish_edit, name='meal_dish_edit'),
    path('dat-com/mon/<int:pk>/xoa/', views.meal_dish_delete, name='meal_dish_delete'),
    path('dat-com/menu/', views.meal_day_menu, name='meal_day_menu'),
    path('dat-com/tong-hop/', views.meal_summary, name='meal_summary'),
    path('dat-com/tong-hop/xuat/', views.meal_summary_export, name='meal_summary_export'),
    path('dat-com/thong-ke/', views.meal_stats, name='meal_stats'),
    path('dat-com/thong-ke/xuat/', views.meal_stats_export, name='meal_stats_export'),
    # Ứng lương
    path('ung-luong/', views.salary_home, name='salary_home'),
    path('ung-luong/quan-ly/', views.salary_manage, name='salary_manage'),
    path('ung-luong/quan-ly/xuat/', views.salary_manage_export, name='salary_manage_export'),
    path('ung-luong/thong-ke/', views.salary_stats, name='salary_stats'),
    path('ung-luong/thong-ke/xuat/', views.salary_stats_export, name='salary_stats_export'),
]
