# training/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # THÊM DÒNG NÀY: Xử lý khi người dùng chỉ gõ /training/
    path('', views.my_courses, name='training_home'),

    # Các dòng cũ giữ nguyên
    path('my-courses/', views.my_courses, name='my_courses'),
    path('course/<int:course_id>/', views.learning_space, name='course_start'),
    path('course/<int:course_id>/lesson/<int:lesson_id>/', views.learning_space, name='learning_space'),
    path('lesson/<int:lesson_id>/complete/', views.mark_lesson_complete, name='mark_lesson_complete'),
    
    path('admin/course/create/', views.course_create, name='course_create'),
]