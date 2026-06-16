import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from assessment.models import Exam

exam = Exam.objects.get(pk=3)
for link in exam.ordered_exam_questions():
    if link.sort_order != 6:
        continue
    q = link.question
    print('question_id=', q.id, 'exam_stt=', link.sort_order)
    for c in q.choices.all():
        print(f'  sort={c.sort_order} id={c.id} text={c.text[:60]!r}')
