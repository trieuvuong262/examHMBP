import os
import sys

sys.path.insert(0, '/app')
os.chdir('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from assessment.models import Exam, ExamSubmission, UserAnswer

exam = Exam.objects.get(pk=3)
print('EXAM:', exam.title)

for sub in ExamSubmission.objects.filter(exam=exam, submitted_at__isnull=False).order_by('-submitted_at'):
    print('---')
    print('user=', sub.user.username, 'auto=', sub.auto_score, 'manual=', sub.manual_score, 'total=', sub.total_score, 'completed=', sub.is_completed)
    mc_sum = 0
    for ans in sub.answers.select_related('question').prefetch_related('selected_choices').order_by('question_id'):
        earned = ans.graded_score or 0
        if ans.question.q_type in ('single', 'multiple'):
            mc_sum += earned
            selected = list(ans.selected_choices.values_list('text', flat=True))
            correct = list(ans.question.choices.filter(is_correct=True).values_list('text', flat=True))
            ok = earned >= ans.question.points
            print(f'  Q{ans.question_id} type={ans.question.q_type} earned={earned}/{ans.question.points} ok={ok}')
            if earned > 0 and not ok:
                print('    BUG stale score? selected=', selected[:2], 'correct=', correct[:2])
            if earned == 0 and selected:
                print('    selected=', [t[:40] for t in selected])
                print('    correct=', [t[:40] for t in correct])
    print('  mc_sum_from_answers=', mc_sum)
