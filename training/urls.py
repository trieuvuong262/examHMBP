from django.urls import path
from . import views

urlpatterns = [
    path('', views.my_courses, name='training_home'),
    path('my-courses/', views.my_courses, name='my_courses'),
    path('course/<int:course_id>/', views.learning_space, name='course_start'),
    path('course/<int:course_id>/lesson/<int:lesson_id>/', views.learning_space, name='learning_space'),
    path('lesson/<int:lesson_id>/complete/', views.mark_lesson_complete, name='mark_lesson_complete'),
    path('admin/course/create/', views.course_create, name='course_create'),
    path('admin/course/', views.course_list, name='course_list'),
    path('admin/course/create/', views.course_create, name='course_create'),
    path('admin/course/<int:course_id>/builder/', views.course_builder, name='course_builder'),
    path('admin/course/<int:course_id>/edit/', views.course_edit, name='course_edit'),
    path('admin/course/<int:course_id>/chapter/add/', views.chapter_create, name='chapter_create'),
    path('admin/chapter/<int:chapter_id>/lesson/add/', views.lesson_create, name='lesson_create'),
    path('admin/lesson/<int:lesson_id>/delete/', views.lesson_delete, name='lesson_delete'),
    path('admin/lesson/update-order/', views.update_lesson_order, name='update_lesson_order'),
    path('admin/lesson/<int:lesson_id>/edit/', views.lesson_edit, name='lesson_edit'),
    # API Quản lý Danh mục Đào tạo
    path('api/categories/', views.api_get_categories, name='api_get_categories'),
    path('api/categories/add/', views.api_add_category, name='api_add_category'),
    path('api/categories/<int:pk>/edit/', views.api_edit_category, name='api_edit_category'),
    path('api/categories/<int:pk>/delete/', views.api_delete_category, name='api_delete_category'),
]