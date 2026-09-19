from training.models import Course, Chapter, Lesson
from assessment.models import Exam, Question, Competency

print('TZ_CHECK')
from django.conf import settings
print('TIME_ZONE', settings.TIME_ZONE)
print('USE_TZ', settings.USE_TZ)

print('COURSES')
for c in Course.objects.order_by('id'):
    nch = c.chapters.count()
    nls = Lesson.objects.filter(chapter__course=c).count()
    nuser = c.assigned_users.count()
    print(c.id, '|', c.title, '| active', c.is_active, '| chapters', nch, '| lessons', nls, '| users', nuser, '| final_exam', c.final_exam_id)

print('COMPETENCIES')
for x in Competency.objects.all()[:20]:
    print(x.id, x.name)

print('EXAMS', Exam.objects.count(), 'QUESTIONS', Question.objects.count())
