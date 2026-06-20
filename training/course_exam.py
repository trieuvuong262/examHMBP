"""Kiểm tra điều kiện làm bài thi cuối khóa."""

from django.urls import reverse

from training.models import Course, Enrollment


def incomplete_courses_blocking_exam(user, exam) -> list[Course]:
    """Khóa học gắn bài thi này mà user chưa hoàn thành."""
    if not getattr(user, 'is_authenticated', False) or exam is None:
        return []

    blockers = []
    courses = (
        Course.objects.filter(
            final_exam=exam,
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
