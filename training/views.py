from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Course, Enrollment

@login_required
def my_courses(request):
    user = request.user
    
    # 1. Lấy tất cả khóa học đang active và được giao cho user này
    assigned_courses = Course.objects.filter(assigned_users=user, is_active=True).order_by('-created_at')
    
    course_data = []
    for course in assigned_courses:
        # 2. Lấy hoặc tự động tạo Enrollment (Ghi danh) để theo dõi tiến độ
        enrollment, created = Enrollment.objects.get_or_create(user=user, course=course)
        
        # 3. Phân loại trạng thái để hiển thị nút bấm cho đúng
        status = 'not_started'
        if enrollment.is_completed:
            status = 'completed'
        elif enrollment.progress_percent > 0:
            status = 'in_progress'

        course_data.append({
            'course': course,
            'progress': enrollment.progress_percent,
            'status': status
        })

    return render(request, 'training/my_courses.html', {
        'course_data': course_data,
        'title': 'Không gian học tập của tôi'
    })