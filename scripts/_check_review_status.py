from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_PRODUCTION

sub = DailyWorkReport.objects.filter(
    report_profile=REPORT_PROFILE_PRODUCTION,
    status=DailyWorkReport.STATUS_SUBMITTED,
).count()
rev = DailyWorkReport.objects.filter(
    report_profile=REPORT_PROFILE_PRODUCTION,
    status=DailyWorkReport.STATUS_SUBMITTED,
    hod_reviewed=True,
).count()
print("submitted", sub, "hod_reviewed", rev, "not_reviewed", sub - rev)
r = DailyWorkReport.objects.filter(pk=3324).first()
if r:
    print("3324", r.status, r.hod_reviewed)
