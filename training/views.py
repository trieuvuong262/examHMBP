from assessment.models import ExamSubmission
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
import json
from urllib.parse import urlencode

from assessment.decorators import module_perm_required
from hrm.module_permissions import (
    MODULE_TRAINING,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_update_module,
)
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import LIST_PAGE_SIZE, paginate_queryset

from .forms import ChapterForm, CourseForm, LessonForm
from .models import Chapter, Course, CourseCategory, Enrollment, Lesson, LessonProgress


def _is_survey_read_mode(next_url: str) -> bool:
    if not next_url:
        return False
    return '/khao-sat/d/' in next_url


def _training_perm_context(user):
    return {
        'can_create': user_can_create_module(user, MODULE_TRAINING),
        'can_update': user_can_update_module(user, MODULE_TRAINING),
        'can_delete': user_can_delete_module(user, MODULE_TRAINING),
        'is_admin': user_can_edit_module(user, MODULE_TRAINING),
    }


@module_perm_required(MODULE_TRAINING, 'view')
def my_courses(request):
    user = request.user
    search_query = get_search_query(request)
    status_filter = request.GET.get('status', '').strip()

    assigned_courses_qs = Course.objects.filter(
        assigned_users=user, is_active=True,
    ).order_by('-created_at')
    assigned_courses_qs = apply_term_search(
        assigned_courses_qs, search_query,
        'title__icontains', 'description__icontains', 'category__name__icontains',
    )
    
    submitted_exam_ids = ExamSubmission.objects.filter(
        user=user, 
        submitted_at__isnull=False
    ).values_list('exam_id', flat=True)

    course_data = []
    for course in assigned_courses_qs:
        enrollment, created = Enrollment.objects.get_or_create(user=user, course=course)
        enrollment.sync_completion_status()

        status = 'not_started'
        if enrollment.is_completed:
            status = 'completed'
        elif enrollment.progress_percent > 0:
            status = 'in_progress'

        if status_filter and status != status_filter:
            continue

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

    paginator = Paginator(course_data, LIST_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    if 'page' in params:
        del params['page']
    query_string = params.urlencode()

    return render(request, 'training/my_courses.html', {
        'course_data': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'status_filter': status_filter,
        'title': 'Không gian học tập của tôi'
    })

@module_perm_required(MODULE_TRAINING, 'view')
def learning_space(request, course_id, lesson_id=None):
    course = get_object_or_404(Course, id=course_id, is_active=True)
    enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
    enrollment.sync_completion_status()

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

    return_next = request.GET.get('next', '').strip()
    if return_next and not url_has_allowed_host_and_scheme(
        return_next,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_next = ''
    survey_read_mode = _is_survey_read_mode(return_next)
    learning_query_suffix = f"?{urlencode({'next': return_next})}" if return_next else ''

    return render(request, 'training/learning_space.html', {
        'course': course,
        'chapters': chapters,
        'current_lesson': current_lesson,
        'completed_lesson_ids': completed_lesson_ids,
        'enrollment': enrollment,
        'next_lesson': next_lesson,
        'return_next': return_next,
        'survey_read_mode': survey_read_mode,
        'learning_query_suffix': learning_query_suffix,
        'title': f'Học tập: {course.title}'
    })

@module_perm_required(MODULE_TRAINING, 'view')
def mark_lesson_complete(request, lesson_id):
    """API dùng AJAX để đánh dấu bài học hoàn tất"""
    if request.method == 'POST':
        return_next = (request.POST.get('next') or '').strip()
        if return_next and not url_has_allowed_host_and_scheme(
            return_next,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return_next = ''
        if _is_survey_read_mode(return_next):
            # Đọc từ khảo sát chỉ để tham khảo, không ghi tiến độ module Đào tạo.
            return JsonResponse({
                'status': 'readonly',
                'redirect_url': return_next,
            })

        lesson = get_object_or_404(Lesson, id=lesson_id)
        
        progress, created = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
        progress.is_completed = True
        progress.save()

        course = lesson.chapter.course
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        is_course_finished = enrollment.sync_completion_status()
        exam_url = None
        redirect_url = None
        if is_course_finished and return_next:
            redirect_url = return_next
        elif is_course_finished and course.final_exam_id:
            from assessment.models import ExamSubmission
            from django.urls import reverse

            already_submitted = ExamSubmission.objects.filter(
                user=request.user,
                exam_id=course.final_exam_id,
                is_completed=True,
            ).exists()
            if not already_submitted:
                exam_url = reverse('take_exam', args=[course.final_exam_id])
                redirect_url = exam_url

        return JsonResponse({
            'status': 'success',
            'progress_percent': enrollment.progress_percent,
            'is_course_finished': is_course_finished,
            'exam_url': exam_url,
            'redirect_url': redirect_url,
        })
    return JsonResponse({'status': 'error'}, status=400)

@module_perm_required(MODULE_TRAINING, 'create')
def course_create(request):
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if hasattr(u, 'profile'):
                # Lưu thành mảng: [Chức danh, Vai trò]
                user_positions[str(u.id)] = [u.profile.position, u.profile.role] 
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
    
@module_perm_required(MODULE_TRAINING, 'edit')
def course_list(request):
    search_query = get_search_query(request)
    category_id = request.GET.get('category', '').strip()
    status = request.GET.get('status', '').strip()

    courses_qs = Course.objects.select_related('category').annotate(
        student_count=Count('assigned_users', distinct=True),
        chapter_count=Count('chapters', distinct=True)
    ).order_by('-created_at')

    courses_qs = apply_term_search(
        courses_qs, search_query,
        'title__icontains', 'description__icontains', 'category__name__icontains',
    )
    if category_id.isdigit():
        courses_qs = courses_qs.filter(category_id=int(category_id))
    if status == 'active':
        courses_qs = courses_qs.filter(is_active=True)
    elif status == 'inactive':
        courses_qs = courses_qs.filter(is_active=False)

    page_obj, query_string = paginate_queryset(request, courses_qs)
    categories = CourseCategory.objects.order_by('name')

    return render(request, 'training/admin/course_list.html', {
        'courses': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'categories': categories,
        'category_id': category_id,
        'status_filter': status,
        'title': 'Quản lý danh sách khóa học',
        **_training_perm_context(request.user),
    })


@module_perm_required(MODULE_TRAINING, 'update')
def course_edit(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    user_positions = {}
    users = User.objects.select_related('profile').all()
    for u in users:
        try:
            if hasattr(u, 'profile'):
                # Lưu thành mảng: [Chức danh, Vai trò]
                user_positions[str(u.id)] = [u.profile.position, u.profile.role]
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
    
@module_perm_required(MODULE_TRAINING, 'edit')
def course_builder(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    chapters = course.chapters.prefetch_related('lessons').all().order_by('order')

    return render(request, 'training/admin/course_builder.html', {
        'course': course,
        'chapters': chapters,
        **_training_perm_context(request.user),
    })


@module_perm_required(MODULE_TRAINING, 'create')
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

@module_perm_required(MODULE_TRAINING, 'create')
def lesson_create(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.chapter = chapter
            lesson.save()
            messages.success(request, f'Đã thêm bài học: {lesson.title}')
            return redirect('course_builder', course_id=chapter.course.id)

        for field, errors in form.errors.items():
            label = field
            if field in form.fields:
                label = form.fields[field].label or field
            for error in errors:
                messages.error(request, f'{label}: {error}')
        for error in form.non_field_errors():
            messages.error(request, str(error))

    return redirect('course_builder', course_id=chapter.course.id)



@module_perm_required(MODULE_TRAINING, 'delete')
@require_POST
def lesson_delete(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course_id = lesson.chapter.course.id
    lesson_title = lesson.title
    lesson.delete()
    messages.success(request, f'Đã xóa bài học: {lesson_title}')
    return redirect('course_builder', course_id=course_id)

@module_perm_required(MODULE_TRAINING, 'update')
@require_POST
def update_lesson_order(request):
    try:
        data = json.loads(request.body)
        lesson_ids = data.get('lesson_ids', [])
        
        for index, l_id in enumerate(lesson_ids):
            Lesson.objects.filter(id=l_id).update(order=index + 1)
            
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    

@module_perm_required(MODULE_TRAINING, 'update')
def lesson_edit(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    course_id = lesson.chapter.course.id 
    
    if request.method == 'POST':
        form = LessonForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():

            form.save() 
            messages.success(request, f'Đã cập nhật bài học: {lesson.title}')
            return redirect('course_builder', course_id=course_id)
    else:
        form = LessonForm(instance=lesson)

    return render(request, 'training/admin/lesson_form.html', {
        'form': form,
        'lesson': lesson,
        'course_id': course_id
    })


@module_perm_required(MODULE_TRAINING, 'edit')
def api_get_categories(request):
    """API lấy danh sách danh mục (Dùng cho Modal AJAX)"""
    categories = CourseCategory.objects.all().order_by('-id').values('id', 'name')
    return JsonResponse({'categories': list(categories)})

@module_perm_required(MODULE_TRAINING, 'create')
@require_POST
def api_add_category(request):
    """API thêm danh mục mới"""
    name = request.POST.get('name', '').strip()
    if name:
        cat = CourseCategory.objects.create(name=name)
        return JsonResponse({'status': 'success', 'id': cat.id, 'name': cat.name})
    return JsonResponse({'status': 'error', 'message': 'Tên không được để trống'}, status=400)

@module_perm_required(MODULE_TRAINING, 'update')
@require_POST
def api_edit_category(request, pk):
    """API sửa tên danh mục"""
    cat = get_object_or_404(CourseCategory, pk=pk)
    name = request.POST.get('name', '').strip()
    if name:
        cat.name = name
        cat.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Tên không được để trống'}, status=400)

@module_perm_required(MODULE_TRAINING, 'delete')
@require_POST
def api_delete_category(request, pk):
    """API xóa danh mục"""
    CourseCategory.objects.filter(pk=pk).delete()
    return JsonResponse({'status': 'success'})