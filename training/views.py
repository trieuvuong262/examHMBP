from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Course, Enrollment
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone
from .models import Course, Chapter, Lesson, Enrollment, LessonProgress
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .forms import CourseForm
import json
from django.contrib.auth.models import User

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
    

@login_required
def learning_space(request, course_id, lesson_id=None):
    course = get_object_or_404(Course, id=course_id, is_active=True)
    enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)

    # Lấy toàn bộ chương và bài học
    chapters = course.chapters.all().prefetch_related('lessons')

    # Xác định bài học hiện tại đang xem
    current_lesson = None
    if lesson_id:
        current_lesson = get_object_or_404(Lesson, id=lesson_id, chapter__course=course)
    else:
        # Nếu không truyền id bài học, lấy bài đầu tiên của chương đầu tiên
        first_chapter = chapters.first()
        if first_chapter:
            current_lesson = first_chapter.lessons.first()

    # Lấy danh sách ID các bài đã hoàn thành để hiển thị tích xanh
    completed_lesson_ids = LessonProgress.objects.filter(
        user=request.user, 
        lesson__chapter__course=course, 
        is_completed=True
    ).values_list('lesson_id', flat=True)

    # Xác định bài học tiếp theo (để làm nút Next)
    next_lesson = None
    if current_lesson:
        all_lessons = list(Lesson.objects.filter(chapter__course=course).order_by('chapter__order', 'order'))
        try:
            current_idx = all_lessons.index(current_lesson)
            if current_idx + 1 < len(all_lessons):
                next_lesson = all_lessons[current_idx + 1]
        except ValueError:
            pass

    return render(request, 'training/learning_space.html', {
        'course': course,
        'chapters': chapters,
        'current_lesson': current_lesson,
        'completed_lesson_ids': completed_lesson_ids,
        'enrollment': enrollment,
        'next_lesson': next_lesson,
        'title': f'Học tập: {course.title}'
    })

@login_required
def mark_lesson_complete(request, lesson_id):
    """API dùng AJAX để đánh dấu bài học hoàn tất"""
    if request.method == 'POST':
        lesson = get_object_or_404(Lesson, id=lesson_id)
        
        # Cập nhật tiến độ bài học
        progress, created = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
        progress.is_completed = True
        progress.save()

        # Cập nhật trạng thái khóa học nếu đạt 100%
        enrollment = Enrollment.objects.get(user=request.user, course=lesson.chapter.course)
        is_course_finished = False
        
        if enrollment.progress_percent >= 100.0:
            enrollment.is_completed = True
            enrollment.completed_at = timezone.now()
            enrollment.save()
            is_course_finished = True

        return JsonResponse({
            'status': 'success',
            'progress_percent': enrollment.progress_percent,
            'is_course_finished': is_course_finished
        })
    return JsonResponse({'status': 'error'}, status=400)

@staff_member_required
def course_create(request):
    # 1. TẠO TỪ ĐIỂN MAP ID_NHÂN_VIÊN VÀ CHỨC DANH
    user_positions = {}
    # Dùng select_related để tối ưu hóa truy vấn DB
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if u.profile.position:
                user_positions[str(u.id)] = u.profile.position
        except:
            pass # Bỏ qua nếu user đó chưa có thông tin profile

    # 2. Xử lý Form như bình thường
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Đã tạo thành công khóa học: {course.title}')
            return redirect('admin_dashboard') 
    else:
        form = CourseForm()

    # 3. Gửi thêm biến user_positions_json ra ngoài file HTML
    return render(request, 'training/admin/course_form.html', {
        'form': form,
        'user_positions_json': json.dumps(user_positions) # Gửi dữ liệu ra frontend
    })