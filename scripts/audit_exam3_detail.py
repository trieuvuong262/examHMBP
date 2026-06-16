import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from assessment.models import Exam, ExamSubmission

exam = Exam.objects.get(pk=3)
print('Questions in exam:')
for link in exam.ordered_exam_questions():
    q = link.question
    correct = list(q.choices.filter(is_correct=True).values_list('id', 'text'))
    print(f'  stt={link.sort_order} id={q.id} type={q.q_type} pts={q.points} correct_count={len(correct)}')
    print(f'    content={q.content[:80]!r}')
    for cid, text in correct:
        print(f'      OK: {text[:60]!r}')

print('\nAll submissions:')
for sub in ExamSubmission.objects.filter(exam=exam).order_by('-submitted_at'):
    print(f'  {sub.user.username}: auto={sub.auto_score} manual={sub.manual_score} total={sub.total_score} completed={sub.is_completed} submitted={sub.submitted_at}')
    for ans in sub.answers.select_related('question').prefetch_related('selected_choices').all():
        sel = list(ans.selected_choices.values_list('id', flat=True))
        cor = list(ans.question.choices.filter(is_correct=True).values_list('id', flat=True))
        earned = ans.graded_score or 0
        match = sorted(sel) == sorted(cor) if ans.question.q_type == 'multiple' else (sel and sel[0] in cor)
        if earned and not match:
            print(f'    SCORE BUG q={ans.question_id} earned={earned} sel={sel} cor={cor}')
        elif earned == 0 and sel and ans.question.q_type in ('single', 'multiple'):
            print(f'    zero ok q={ans.question_id} sel={sel[:3]} cor={cor[:3]}')
