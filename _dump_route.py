import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()
u = User.objects.filter(is_superuser=True).first() or User.objects.filter(username="admin").first()
print("user", getattr(u, "username", None), "id", getattr(u, "pk", None))
c = Client(HTTP_HOST="127.0.0.1")
if u:
    c.force_login(u)
r = c.get("/san-xuat/ke-hoach/bang/?mode=list&tab=route")
print("status", r.status_code, "len", len(r.content))
html = r.content.decode("utf-8", "replace")
out = r"d:\Project\PortalJustPlay\_route_dump.html"
open(out, "w", encoding="utf-8").write(html)
print("has jp-tl-sheet", "jp-tl-sheet" in html)
print("has lo-trinh", 'id="lo-trinh"' in html)
print("has jp-tl-bar", "jp-tl-bar" in html)
print("has c-dept", "c-dept" in html)
print("has jp-tl-chart", "jp-tl-chart" in html)
i = html.find("jp-tl-sheet")
print("idx", i)
if i >= 0:
    snippet = html[i : i + 1200]
    open(r"d:\Project\PortalJustPlay\_route_snip.txt", "w", encoding="utf-8").write(snippet)
    print("wrote snip")
