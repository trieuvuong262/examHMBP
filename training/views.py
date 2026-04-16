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
from django.db.models import Count
from .forms import ChapterForm, LessonForm
from django.views.decorators.http import require_POST


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
    
@staff_member_required
def course_list(request):
    # Lấy danh sách khóa học, đếm luôn số học viên và số chương để hiển thị cho tiện
    courses = Course.objects.annotate(
        student_count=Count('assigned_users', distinct=True),
        chapter_count=Count('chapters', distinct=True)
    ).order_by('-created_at')

    return render(request, 'training/admin/course_list.html', {
        'courses': courses,
        'title': 'Quản lý danh sách khóa học'
    })
@staff_member_required
def course_edit(request, course_id):
    # Lấy khóa học từ DB
    course = get_object_or_404(Course, id=course_id)
    
    # 1. TẠO TỪ ĐIỂN CHỨC DANH ĐỂ DÙNG SELECT2 (giống hệt bên tạo mới)
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if hasattr(u, 'profile') and u.profile.position:
                user_positions[str(u.id)] = u.profile.position
        except:
            pass

    # 2. XỬ LÝ FORM SỬA DỮ LIỆU
    if request.method == 'POST':
        # Thêm instance=course để ghi đè dữ liệu cũ
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã cập nhật thông tin khóa học: {course.title}')
            return redirect('course_list')
    else:
        # Load dữ liệu cũ vào form
        form = CourseForm(instance=course)

    # 3. DÙNG CHUNG FILE GIAO DIỆN course_form.html
    return render(request, 'training/admin/course_form.html', {
        'form': form,
        'user_positions_json': json.dumps(user_positions)
    })
    
@staff_member_required
def course_builder(request, course_id):
    # Lấy thông tin khóa học hiện tại
    course = get_object_or_404(Course, id=course_id)
    
    # Lấy tất cả các chương của khóa học này, kèm theo các bài học bên trong (dùng prefetch_related để tối ưu truy vấn)
    chapters = course.chapters.prefetch_related('lessons').all().order_by('order')

    return render(request, 'training/admin/course_builder.html', {
        'course': course,
        'chapters': chapters,
    })
    

@staff_member_required
def chapter_create(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if request.method == 'POST':
        form = ChapterForm(request.POST)
        if form.is_valid():
            chapter = form.save(commit=False)
            chapter.course = course
            chapter.save()
            return redirect('course_builder', course_id=course.id)
    return redirect('course_builder', course_id=course.id)

@staff_member_required
def lesson_create(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.chapter = chapter
            lesson.save()
            return redirect('course_builder', course_id=chapter.course.id)
    return redirect('course_builder', course_id=chapter.course.id)



# --- XÓA BÀI HỌC ---
@staff_member_required
@require_POST
def lesson_delete(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course_id = lesson.chapter.course.id
    lesson_title = lesson.title
    lesson.delete()
    messages.success(request, f'Đã xóa bài học: {lesson_title}')
    return redirect('course_builder', course_id=course_id)

# --- CẬP NHẬT THỨ TỰ BÀI HỌC (AJAX KÉO THẢ) ---
@staff_member_required
@require_POST
def update_lesson_order(request):
    try:
        data = json.loads(request.body)
        lesson_ids = data.get('lesson_ids', [])
        
        # Cập nhật lại cột 'order' cho từng ID gửi lên
        for index, l_id in enumerate(lesson_ids):
            Lesson.objects.filter(id=l_id).update(order=index + 1)
            
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
# Đảm bảo bạn đã import messages ở đầu file: from django.contrib import messages

@staff_member_required
def lesson_edit(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course_id = lesson.chapter.course.id 
    
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            # --- ĐOẠN SỬA LỖI VIDEO 153 TẠI ĐÂY ---
            new_lesson = form.save(commit=False)
            video_url = form.cleaned_data.get('video_url')
            if video_url and "youtube.com/watch?v=" in video_url:
                video_id = video_url.split("v=")[1].split("&")[0]
                # Sử dụng youtube-nocookie để tránh lỗi 153 do chặn cookie bên thứ 3
                new_lesson.video_url = f"https://www.youtube-nocookie.com/embed/{video_id}"
            new_lesson.save()
            # --------------------------------------
            messages.success(request, f'Đã cập nhật bài học: {lesson.title}')
            return redirect('course_builder', course_id=course_id)
    else:
        form = LessonForm(instance=lesson)

    return render(request, 'training/admin/lesson_form.html', {
        'form': form,
        'lesson': lesson,
        'course_id': course_id
    })