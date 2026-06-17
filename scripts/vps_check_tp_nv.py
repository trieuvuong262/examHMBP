from django.contrib.auth import get_user_model
from hrm.permissions import get_report_team_users, can_review_user_report
from reports.models import DailyWorkReport

User = get_user_model()
tp = User.objects.get(username='tp.tb')
nv = User.objects.get(username='nv.tb')
print('tp team:', list(get_report_team_users(tp).values_list('username', flat=True)))
print('can_review tp->nv:', can_review_user_report(tp, DailyWorkReport(employee=nv)))
print('nv id:', nv.pk)
