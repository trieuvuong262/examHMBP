"""Trace SX today view 500 — pipe to manage.py shell."""
import traceback

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()
user = User.objects.filter(username="ntloan").first() or User.objects.filter(is_active=True).first()
print("user", user.username if user else None)

c = Client(HTTP_HOST="portal.justplay.vn")
if user:
    c.force_login(user)

urls = [
    "/reports/sx/today/?date=2026-07-08&shift=MORNING&phase=review",
    "/reports/sx/today/?date=2026-07-08&shift=MORNING",
    "/reports/sx/3324/?from=2026-06-29&to=2026-07-08",
]

for url in urls:
    print("---", url)
    try:
        r = c.get(url)
        print("status", r.status_code)
        if r.status_code >= 500:
            print(r.content.decode("utf-8", errors="replace")[:2500])
    except Exception:
        traceback.print_exc()

# POST submit
if user:
    print("--- POST submit")
    try:
        r = c.post(
            "/reports/sx/today/?date=2026-07-08&shift=MORNING",
            {"action": "submit", "declared_work_hours": "9.5", "shift": "MORNING"},
        )
        print("status", r.status_code, "loc", r.get("Location"))
        if r.status_code >= 500:
            print(r.content.decode("utf-8", errors="replace")[:2500])
    except Exception:
        traceback.print_exc()
