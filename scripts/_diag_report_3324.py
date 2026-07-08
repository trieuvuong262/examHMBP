"""Diagnose report detail 500 — run: python manage.py shell < scripts/_diag_report_3324.py"""
import traceback

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from reports.models import DailyWorkReport
from reports.production_hourly import build_hourly_grid, build_productivity_report
from reports.views import _report_detail_core

PK = 3324

report = DailyWorkReport.objects.filter(pk=PK).first()
print("report:", report)
if not report:
    raise SystemExit("not found")

print("profile:", report.report_profile, "shift:", report.shift, "shift_started_at:", report.shift_started_at)

try:
    grid = build_hourly_grid(report)
    print("hourly_grid rows:", len(grid.get("rows") or []))
except Exception:
    print("build_hourly_grid FAILED:")
    traceback.print_exc()

try:
    prod = build_productivity_report(report)
    print("productivity has_data:", prod.get("has_data"))
    print("day_summary:", prod.get("day_summary"))
except Exception:
    print("build_productivity_report FAILED:")
    traceback.print_exc()

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()
print("user:", user)

factory = RequestFactory()
request = factory.get(f"/reports/sx/{PK}/")
request.user = user

try:
    resp = _report_detail_core(request, PK, detail_url_name="reports:detail_cn")
    print("view status:", getattr(resp, "status_code", type(resp).__name__))
except Exception:
    print("_report_detail_core FAILED:")
    traceback.print_exc()
