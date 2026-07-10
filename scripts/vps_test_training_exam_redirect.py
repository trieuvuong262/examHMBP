"""Test redirect thi cuối khóa sau khi hoàn thành bài học — chạy: python manage.py shell < scripts/vps_test_training_exam_redirect.py"""
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from assessment.models import ExamSubmission
from training.models import Course, Enrollment, Lesson, LessonProgress
from training.views import _is_survey_read_mode

User = get_user_model()
user = User.objects.filter(is_active=True).exclude(username='admin').first()
if not user:
    user = User.objects.filter(is_superuser=True).first()
print('user:', user.username if user else 'NONE')

course = (
    Course.objects.filter(is_active=True, final_exam__isnull=False, assigned_users=user)
    .prefetch_related('chapters__lessons')
    .first()
)
if not course:
    course = Course.objects.filter(is_active=True, final_exam__isnull=False).first()
    if course and user:
        course.assigned_users.add(user)
print('course:', course.title if course else 'NONE', 'exam:', course.final_exam_id if course else None)

if not course or not user:
    print('SKIP — thiếu user/khóa có bài thi cuối')
    raise SystemExit(0)

lessons = list(Lesson.objects.filter(chapter__course=course).order_by('chapter__order', 'order'))
print('lessons:', len(lessons))
if not lessons:
    print('SKIP — khóa không có bài học')
    raise SystemExit(0)

LessonProgress.objects.filter(user=user, lesson__chapter__course=course).delete()
enrollment, _ = Enrollment.objects.get_or_create(user=user, course=course)
enrollment.is_completed = False
enrollment.completed_at = None
enrollment.save(update_fields=['is_completed', 'completed_at'])
ExamSubmission.objects.filter(user=user, exam_id=course.final_exam_id).delete()

c = Client()
c.force_login(user)
last = lessons[-1]
url = reverse('learning_space', args=[course.pk, last.pk])
print('survey_mode_menu:', _is_survey_read_mode())
print('survey_mode_ref:', _is_survey_read_mode(ref='survey'))
print('survey_mode_next:', _is_survey_read_mode(next_url='/khao-sat/d/test/'))

r = c.post(
    reverse('mark_lesson_complete', args=[last.pk]),
    {'next': '', 'ref': ''},
    HTTP_HOST='portal.justplay.vn',
)
print('POST menu path:', r.status_code, r.json())

for lesson in lessons:
    LessonProgress.objects.update_or_create(
        user=user,
        lesson=lesson,
        defaults={'is_completed': True},
    )
enrollment.sync_completion_status()
r2 = c.post(
    reverse('mark_lesson_complete', args=[last.pk]),
    {'next': '', 'ref': ''},
    HTTP_HOST='portal.justplay.vn',
)
data2 = r2.json()
print('POST menu last lesson:', r2.status_code, data2)
print('expects_exam_redirect:', bool(data2.get('redirect_url') or data2.get('exam_url')))

r3 = c.post(
    reverse('mark_lesson_complete', args=[last.pk]),
    {'next': '/khao-sat/d/demo/', 'ref': 'survey'},
    HTTP_HOST='portal.justplay.vn',
)
print('POST survey path:', r3.status_code, r3.json())
print('DONE')
