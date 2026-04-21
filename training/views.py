from django.contrib.auth.decorators import login_required
from assessment.models import ExamSubmission
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone
from .models import Course, Chapter, Lesson, Enrollment, LessonProgress
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .forms import CourseForm
import json
from django.contrib.auth.models import User
from django.db.models import Count
from .forms import ChapterForm, LessonForm
from django.views.decorators.http import require_POST
from assessment.decorators import admin_only
import logging
logger = logging.getLogger(__name__)

@login_required
def my_courses(request):
    user = request.user
    
    assigned_courses = Course.objects.filter(assigned_users=user, is_active=True).order_by('-created_at')
    
    submitted_exam_ids = ExamSubmission.objects.filter(
        user=user, 
        submitted_at__isnull=False
    ).values_list('exam_id', flat=True)

    course_data = []
    for course in assigned_courses:
        enrollment, created = Enrollment.objects.get_or_create(user=user, course=course)
        
        status = 'not_started'
        if enrollment.is_completed:
            status = 'completed'
        elif enrollment.progress_percent > 0:
            status = 'in_progress'

        has_taken_exam = False
        final_exam_id = None
        if course.final_exam:
            final_exam_id = course.final_exam.id
            if final_exam_id in submitted_exam_ids:
                has_taken_exam = True

        course_data.append({
            'course': course,
            'progress': enrollment.progress_percent,
            'status': status,
            'has_taken_exam': has_taken_exam,
            'final_exam_id': final_exam_id  
        })

    return render(request, 'training/my_courses.html', {
        'course_data': course_data,
        'title': 'Không gian học tập của tôi'
    })


@admin_only
def course_create(request):
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if u.profile.position:
                user_positions[str(u.id)] = u.profile.position
        except:
            pass 

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Đã tạo thành công khóa học: {course.title}')
            return redirect('admin_dashboard') 
    else:
        form = CourseForm()

    return render(request, 'training/admin/course_form.html', {
        'form': form,
        'user_positions_json': json.dumps(user_positions)
    })
    
@admin_only
def course_list(request):
    courses = Course.objects.annotate(
        student_count=Count('assigned_users', distinct=True),
        chapter_count=Count('chapters', distinct=True)
    ).order_by('-created_at')

    return render(request, 'training/admin/course_list.html', {
        'courses': courses,
        'title': 'Quản lý danh sách khóa học'
    })
@admin_only
def course_edit(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if hasattr(u, 'profile') and u.profile.position:
                user_positions[str(u.id)] = u.profile.position
        except:
            pass

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã cập nhật thông tin khóa học: {course.title}')
            return redirect('course_list')
    else:
        form = CourseForm(instance=course)

    return render(request, 'training/admin/course_form.html', {
        'form': form,
        'user_positions_json': json.dumps(user_positions)
    })
    
@admin_only
def course_builder(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    chapters = course.chapters.prefetch_related('lessons').all().order_by('order')

    return render(request, 'training/admin/course_builder.html', {
        'course': course,
        'chapters': chapters,
    })
    

@admin_only
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

@admin_only
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



@admin_only
@require_POST
def lesson_delete(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course_id = lesson.chapter.course.id
    lesson_title = lesson.title
    lesson.delete()
    messages.success(request, f'Đã xóa bài học: {lesson_title}')
    return redirect('course_builder', course_id=course_id)


@login_required
def learning_space(request, course_id, lesson_id=None):
    course = get_object_or_404(Course, id=course_id, is_active=True)
    
    # ==========================================
    # VÁ LỖI 6 (IDOR): Kiểm tra quyền truy cập!
    # Nếu không phải Admin VÀ không nằm trong danh sách được gán -> Đuổi ra ngoài
    # ==========================================
    if not request.user.is_staff and not course.assigned_users.filter(id=request.user.id).exists():
        messages.error(request, "Truy cập bị từ chối: Bạn chưa được ghi danh vào khóa học này!")
        return redirect('my_courses')

    enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
    chapters = course.chapters.all().prefetch_related('lessons')

    current_lesson = None
    if lesson_id:
        current_lesson = get_object_or_404(Lesson, id=lesson_id, chapter__course=course)
    else:
        first_chapter = chapters.first()
        if first_chapter:
            current_lesson = first_chapter.lessons.first()

    completed_lesson_ids = LessonProgress.objects.filter(
        user=request.user, 
        lesson__chapter__course=course, 
        is_completed=True
    ).values_list('lesson_id', flat=True)

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
@require_POST # VÁ LỖI: Ép buộc API này chỉ nhận POST
def mark_lesson_complete(request, lesson_id):
    """API dùng AJAX để đánh dấu bài học hoàn tất"""
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id)
        
        # VÁ LỖI SẬP SERVER: Dùng filter().first() thay vì get() để tránh lỗi DoesNotExist
        enrollment = Enrollment.objects.filter(user=request.user, course=lesson.chapter.course).first()
        
        if not enrollment:
            return JsonResponse({'status': 'error', 'message': 'Bạn chưa ghi danh khóa học này.'}, status=403)

        progress, created = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
        progress.is_completed = True
        progress.save()

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
    except Exception as e:
        logger.error(f"Lỗi API mark_complete: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Lỗi máy chủ.'}, status=500)


@admin_only
@require_POST
def update_lesson_order(request):
    try:
        data = json.loads(request.body)
        lesson_ids = data.get('lesson_ids', [])
        
        for index, l_id in enumerate(lesson_ids):
            Lesson.objects.filter(id=l_id).update(order=index + 1)
            
        return JsonResponse({'status': 'success'})
    except Exception as e:
        # VÁ LỖI 12: Giấu nhẹm lỗi hệ thống, chỉ log ngầm
        logger.error(f"Lỗi update lesson order: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Lỗi xử lý dữ liệu.'}, status=400)


@admin_only
def lesson_edit(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course_id = lesson.chapter.course.id 
    
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            new_lesson = form.save(commit=False)
            video_url = form.cleaned_data.get('video_url')
            
            # VÁ LỖI: Tránh sập server nếu user nhập link Youtube sai định dạng
            if video_url and "youtube.com/watch?v=" in video_url:
                try:
                    video_id = video_url.split("v=")[1].split("&")[0]
                    new_lesson.video_url = f"https://www.youtube-nocookie.com/embed/{video_id}"
                except IndexError:
                    pass # Link lỗi thì giữ nguyên gốc, không làm sập chức năng lưu

            new_lesson.save()
            messages.success(request, f'Đã cập nhật bài học: {lesson.title}')
            return redirect('course_builder', course_id=course_id)
    else:
        form = LessonForm(instance=lesson)

    return render(request, 'training/admin/lesson_form.html', {
        'form': form,
        'lesson': lesson,
        'course_id': course_id
    })