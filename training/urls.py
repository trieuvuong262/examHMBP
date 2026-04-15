from django.urls import path
from . import views

urlpatterns = [
    # Trang danh sách khóa học (Đã làm ở bước trước)
    path('my-courses/', views.my_courses, name='my_courses'),
    
    # Không gian học tập
    path('course/<int:course_id>/', views.learning_space, name='course_start'),
    path('course/<int:course_id>/lesson/<int:lesson_id>/', views.learning_space, name='learning_space'),
    
    # API Đánh dấu hoàn thành bài học
    path('lesson/<int:lesson_id>/complete/', views.mark_lesson_complete, name='mark_lesson_complete'),
]