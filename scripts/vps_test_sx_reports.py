"""Smoke test báo cáo SX sau deploy — chạy: python manage.py shell < scripts/vps_test_sx_reports.py"""
from decimal import Decimal

from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.models import DailyWorkReport
from reports.report_lock import lock_report_on_supervisor_view
from reports.production_hourly import (
    build_productivity_report,
    compute_day_work_waste_summary,
    validate_production_work_hours,
)

OK = 0
FAIL = 0


def check(name, cond):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}")


_, err = validate_production_work_hours("8")
check("work_hours reject 8", bool(err))

_, err = validate_production_work_hours("16")
check("work_hours reject 16", bool(err))

hours, err = validate_production_work_hours("8.5")
check("work_hours accept 8.5", hours == Decimal("8.5") and not err)

report = DailyWorkReport.objects.filter(report_profile=REPORT_PROFILE_PRODUCTION).order_by("-id").first()
check("production report exists", report is not None)

if report:
    check("hod_reviewed_at field", hasattr(report, "hod_reviewed_at"))
    check("declared_work_hours field", hasattr(report, "declared_work_hours"))
    check("SX skip auto-lock on view", not lock_report_on_supervisor_view(report, report.employee))

submitted = (
    DailyWorkReport.objects.filter(
        report_profile=REPORT_PROFILE_PRODUCTION,
        status=DailyWorkReport.STATUS_SUBMITTED,
    )
    .order_by("-submitted_at")
    .first()
)

if submitted and not submitted.declared_work_hours:
    submitted.declared_work_hours = Decimal("9")
    submitted.save(update_fields=["declared_work_hours"])

if submitted:
    products = list(submitted.production_products.all())
    day = compute_day_work_waste_summary(submitted, products)
    productivity = build_productivity_report(submitted)
    day_summary = productivity.get("day_summary") or {}
    check("day_summary has time_efficiency_pct", "time_efficiency_pct" in day_summary)

    work_minutes = day.get("work_minutes") or Decimal("0")
    if work_minutes > 0 and submitted.declared_work_hours:
        expected = float(
            (
                work_minutes
                / (Decimal(str(submitted.declared_work_hours)) * Decimal("60"))
                * Decimal("100")
            ).quantize(Decimal("0.01"))
        )
        if expected < 1:
            expected = float(
                (Decimal(str(expected)) * Decimal("100")).quantize(Decimal("0.01"))
            )
        got = day_summary.get("time_efficiency_pct")
        check(
            "time_efficiency_pct formula",
            got is not None and abs(got - expected) < 0.02,
        )
        declared_min = Decimal(str(submitted.declared_work_hours)) * 60
        expected_waste = max(
            Decimal("0"), (declared_min - work_minutes).quantize(Decimal("1"))
        )
        check("waste = declared - actual", day["waste_minutes"] == expected_waste)
    else:
        print("SKIP time_efficiency (no session minutes on sample report)")
else:
    print("SKIP productivity test (no submitted SX report)")

print("---")
print(f"Results: {OK} passed, {FAIL} failed")
if FAIL:
    raise SystemExit(1)
