from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory

from san_xuat.views_hub import plan_progress_monitor

User = get_user_model()
u = User.objects.filter(is_superuser=True).first() or User.objects.first()
assert u, "No user"

rf = RequestFactory()
params = {
    "view": "kanban",
    "date_from": "2026-08-05",
    "date_to": "2026-08-05",
    "month": "2026-08",
    "product_code": "",
    "team_label": "",
}
req = rf.get("/san-xuat/ke-hoach/giam-sat-tien-do/", params)
req.user = u
resp = plan_progress_monitor(req)
print("VIEW", resp.status_code, len(resp.content))
print("HAS_KANBAN", b"jp-prog-kanban" in resp.content)

c = Client()
c.force_login(u)
http = c.get("/san-xuat/ke-hoach/giam-sat-tien-do/", params)
print("HTTP", http.status_code, len(http.content))
print("HTTP_KANBAN", b"jp-prog-kanban" in http.content)
print("OK")
