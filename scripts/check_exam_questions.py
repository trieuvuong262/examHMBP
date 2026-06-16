import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from assessment.models import Exam

pk = int(sys.argv[1]) if len(sys.argv) > 1 else 3
exam = Exam.objects.filter(pk=pk).first()
if not exam:
    print(f'Exam id={pk} not found')
    raise SystemExit(1)
print(f'exam_id={exam.id} title={exam.title!r}')
print(f'question_count={exam.questions.count()}')
for q in exam.questions.all().order_by('id'):
    print(f'  - id={q.id} points={q.points} type={q.q_type} content={q.content[:60]!r}...')
