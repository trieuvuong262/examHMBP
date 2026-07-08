from django.contrib.auth import get_user_model
from django.test import RequestFactory

from reports.models import DailyWorkReport
from reports.views import _report_detail_core
from reports.production_hourly import can_edit_production_norms

User = get_user_model()
report = DailyWorkReport.objects.get(pk=3324)
user = User.objects.get(username="admin")
print("report hod_reviewed:", report.hod_reviewed)
print("can_edit_norm admin:", can_edit_production_norms(user, report))
print("can_unapprove expected:", report.hod_reviewed and report.status == "SUBMITTED")
