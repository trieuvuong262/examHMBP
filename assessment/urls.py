# assessment/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Trang danh sách các kỳ thi
    path('exams/', views.exam_list, name='exam_list'),
    
    # Trang làm một bài thi cụ thể (ví dụ: /exams/5/take/)
    path('exams/<int:exam_id>/take/', views.take_exam, name='take_exam'),
]