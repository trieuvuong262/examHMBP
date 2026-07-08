"""HTTP-level SX submit test — pipe: python manage.py shell < scripts/_diag_submit_http.py"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client

from reports.models import DailyWorkReport, ProductionShiftProduct
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()

# Prefer draft with data; else create minimal test path
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
    print("NO_DRAFT")
    raise SystemExit(0)

products = report.production_products.filter(
    status=ProductionShiftProduct.STATUS_DONE,
).count()
print("report_id", report.pk, "user", report.employee.username, "products_done", products)

client = Client()
client.force_login(report.employee)
url = f"/reports/today/cn/{report.report_date.isoformat()}/?date={report.report_date.isoformat()}&shift={report.shift or 'MORNING'}&phase=review"
print("GET", url)
resp = client.get(url)
print("GET status", resp.status_code)
if resp.status_code >= 500:
    print(resp.content[:2000].decode("utf-8", errors="replace"))
    raise SystemExit(1)

post_url = f"/reports/today/cn/{report.report_date.isoformat()}/?date={report.report_date.isoformat()}&shift={report.shift or 'MORNING'}"
print("POST submit", post_url)
resp2 = client.post(
    post_url,
    {
        "action": "submit",
        "declared_work_hours": "9.5",
        "shift": report.shift or "MORNING",
    },
    follow=False,
)
print("POST status", resp2.status_code, "location", resp2.get("Location", ""))
if resp2.status_code >= 500:
    print(resp2.content[:3000].decode("utf-8", errors="replace"))
    raise SystemExit(1)

if resp2.status_code in (301, 302):
    loc = resp2["Location"]
    print("FOLLOW", loc)
    resp3 = client.get(loc)
    print("FOLLOW status", resp3.status_code)
    if resp3.status_code >= 500:
        print(resp3.content[:3000].decode("utf-8", errors="replace"))
        raise SystemExit(1)

print("OK")
