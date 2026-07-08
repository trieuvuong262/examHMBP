from decimal import Decimal

from django.contrib.auth import get_user_model

from reports.models import DailyWorkReport
from reports.production_hourly import (
    build_productivity_report,
    can_edit_production_norms,
    can_edit_production_report,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from hrm.permissions import can_submit_daily_report, can_review_user_report

User = get_user_model()
report = DailyWorkReport.objects.get(pk=3284)
user = User.objects.get(username="admin")

prod = build_productivity_report(report)
print("day_summary", prod.get("day_summary"))
print("hod_reviewed", report.hod_reviewed, "hod_reviewed_at", report.hod_reviewed_at)
print("can_edit_norm", can_edit_production_norms(user, report))
print("can_edit_prod", can_edit_production_report(user, report, can_submit=can_submit_daily_report(user)))
print("can_review", can_review_user_report(user, report))
