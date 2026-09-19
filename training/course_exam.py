"""Kiểm tra điều kiện làm bài thi cuối khóa."""

from django.db.models import Q
from django.urls import reverse

from training.models import Course, Enrollment


def source_exam_of(exam):
    return getattr(exam, 'retry_of', None) or exam


def exam_to_take_for_course(user, course):
    """Đề học viên phải làm: đề thi lại nếu đã trượt, không thì đề chính."""
    exam = getattr(course, 'final_exam', None)
    if exam is None or not getattr(user, 'is_authenticated', False):
        return exam
    retry = exam.retry_exams.filter(is_active=True).first()
    if retry and retry.assigned_users.filter(pk=user.pk).exists():
        from assessment.models import Certificate

        passed = Certificate.objects.filter(
            user=user, exam=retry, is_revoked=False,
        ).exists()
        if not passed:
            return retry
    return exam


def incomplete_courses_blocking_exam(user, exam) -> list[Course]:
    """Khóa học gắn bài thi này mà user chưa hoàn thành."""
    if not getattr(user, 'is_authenticated', False) or exam is None:
        return []

    source = source_exam_of(exam)
    blockers = []
    courses = (
        Course.objects.filter(
            final_exam=source,
            is_active=True,
            assigned_users=user,
        )
        .order_by('title')
    )
    for course in courses:
        enrollment, _ = Enrollment.objects.get_or_create(user=user, course=course)
        enrollment.sync_completion_status()
        if not enrollment.is_completed:
            blockers.append(course)
    return blockers


def learning_url_for_course(course) -> str:
    return reverse('course_start', args=[course.pk])


def reset_course_progress_for_exam(user, exam) -> list:
    """Xóa tiến độ học các khóa gắn bài thi này — bắt học lại rồi mới được thi lại."""
    from training.models import LessonProgress

    source = source_exam_of(exam)
    courses = list(
        Course.objects.filter(final_exam=source)
        .filter(Q(assigned_users=user) | Q(enrolled_students__user=user))
        .distinct()
        .order_by('title')
    )
    for course in courses:
        LessonProgress.objects.filter(
            user=user,
            lesson__chapter__course=course,
        ).delete()
        Enrollment.objects.filter(user=user, course=course).update(
            is_completed=False,
            completed_at=None,
        )
    return courses
