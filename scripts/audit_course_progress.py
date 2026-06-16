#!/usr/bin/env python3
"""Kiểm tra tiến độ / trạng thái hoàn thành khóa học."""
import argparse
import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from training.models import Course, Enrollment, Lesson, LessonProgress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--course-id', type=int, required=True)
    args = parser.parse_args()

    course = Course.objects.get(pk=args.course_id)
    lessons = list(
        Lesson.objects.filter(chapter__course=course)
        .order_by('chapter__order', 'order')
        .values_list('id', 'title', 'chapter__title')
    )
    print(f'Course {course.id}: {course.title}')
    print(f'  final_exam_id={course.final_exam_id}')
    print(f'  total_lessons={len(lessons)}')
    for lid, title, ch in lessons:
        print(f'    L{lid} [{ch}] {title[:60]}')

    print('\nEnrollments:')
    for en in Enrollment.objects.filter(course=course).select_related('user').order_by('user__username'):
        completed_ids = set(
            LessonProgress.objects.filter(
                user=en.user,
                lesson__chapter__course=course,
                is_completed=True,
            ).values_list('lesson_id', flat=True)
        )
        missing = [lid for lid, _, _ in lessons if lid not in completed_ids]
        prog = en.progress_percent
        print(
            f'  {en.user.username}: progress={prog}% is_completed={en.is_completed} '
            f'completed={len(completed_ids)}/{len(lessons)} missing_lesson_ids={missing}'
        )


if __name__ == '__main__':
    main()
