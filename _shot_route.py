import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from playwright.sync_api import sync_playwright

User = get_user_model()
u = User.objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST="127.0.0.1")
c.force_login(u)
sid = c.cookies["sessionid"].value
url = "http://127.0.0.1:8000/san-xuat/ke-hoach/bang/?mode=list&tab=route"
out = r"d:\Project\PortalJustPlay\_route_shot.png"

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 900})
    context.add_cookies([{
        "name": "sessionid",
        "value": sid,
        "url": "http://127.0.0.1:8000",
    }])
    page = context.new_page()
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.screenshot(path=out, full_page=False)
    table = page.locator(".jp-tl-sheet")
    print("table count", table.count())
    if table.count():
        table.first.screenshot(path=r"d:\Project\PortalJustPlay\_route_table.png")
        box = table.first.bounding_box()
        print("table box", box)
    wrap = page.locator("#lo-trinh")
    print("lo-trinh count", wrap.count())
    if wrap.count():
        wrap.first.screenshot(path=r"d:\Project\PortalJustPlay\_route_lotrinh.png")
    print("title", page.title())
    print("url", page.url)
    browser.close()
print("done")
