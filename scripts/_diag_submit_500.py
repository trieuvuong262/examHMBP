"""Diagnose SX submit 500 — run: python manage.py shell < scripts/_diag_submit_500.py"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from decimal import Decimal
from django.test import RequestFactory
from django.contrib.auth import get_user_model

from reports.models import DailyWorkReport
from reports.production_hourly import (
    build_hourly_grid,
    validate_production_work_hours,
    lock_production_steps_on_submit,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.views import _finalize_report_submission
from reports.views_production_hourly import _handle_production_post, _load_production_report

User = get_user_model()
report = (
    DailyWorkReport.objects.filter(
        report_profile=REPORT_PROFILE_PRODUCTION,
        status=DailyWorkReport.STATUS_DRAFT,
    )
    .select_related("employee")
    .order_by("-updated_at")
    .first()
)
if not report:
    print("NO_DRAFT_REPORT")
    raise SystemExit(0)

print("report_id", report.pk, "employee", report.employee.username, "shift", report.shift)
wh, err = validate_production_work_hours("9.5")
print("validate_9.5", wh, err)
grid = build_hourly_grid(report)
print("grid_rows", len(grid.get("rows") or []), "grand_total", grid.get("grand_total"))

try:
    lock_production_steps_on_submit(report)
    print("lock_ok")
except Exception as exc:
    print("lock_FAIL", type(exc).__name__, exc)

rf = RequestFactory()
req = rf.post(
    f"/reports/today/cn/{report.report_date}/",
    {
        "action": "submit",
        "declared_work_hours": "9.5",
        "shift": report.shift or "MORNING",
    },
)
req.user = report.employee
try:
    result = _handle_production_post(
        req,
        report,
        report.report_date,
        report.employee,
        editing_for_other=False,
        shift=report.shift or "MORNING",
    )
    print("handle_result", result)
except Exception as exc:
    import traceback

    print("handle_FAIL", type(exc).__name__, exc)
    traceback.print_exc()
