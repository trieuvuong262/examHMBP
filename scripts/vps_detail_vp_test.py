import sys
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from hrm.permissions import can_view_user_report
from reports.models import DailyWorkReport

User = get_user_model()
HOST = 'portal.justplay.vn'
report = DailyWorkReport.objects.get(pk=34)
print('Report:', report.pk, report.employee.username, report.report_profile)

for uname in ['tp.tb', 'Thoptt', 'Ductn', 'Dinhgiang']:
    u = User.objects.filter(username=uname).first()
    if not u:
        continue
    can = can_view_user_report(u, report)
    c = Client(HTTP_HOST=HOST)
    c.force_login(u)
    r = c.get(reverse('reports:detail_vp', args=[34]))
    print(f'{uname}: can_view={can} detail_vp={r.status_code} url={getattr(r,"url","")}')
