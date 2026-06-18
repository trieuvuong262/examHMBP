from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE
o = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_OFFICE).order_by('-report_date').first()
if o:
    print(o.pk, o.employee.username, o.report_date, o.report_profile, o.status)
else:
    print('no office report')
