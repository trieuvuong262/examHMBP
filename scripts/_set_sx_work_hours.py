from decimal import Decimal

from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_PRODUCTION

n = DailyWorkReport.objects.filter(
    report_profile=REPORT_PROFILE_PRODUCTION,
).update(declared_work_hours=Decimal("9.5"))
print("Updated", n, "SX reports to 9.5h (9h30)")
