"""Kiểm tra HTML render + cấu trúc expand cây thư mục trên VPS."""
import os
import re
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
django.setup()

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


def main():
    host = settings.ALLOWED_HOSTS[0]
    user = User.objects.filter(is_superuser=True).first()
    client = Client(HTTP_HOST=host)
    client.force_login(user)
    html = client.get(reverse("nas_storage:folder_list"), HTTP_HOST=host).content.decode()

    checks = [
        ("data-folder-target in HTML", "data-folder-target=" in html),
        ("kids hidden by default", 'class="jp-folder-tree-kids d-none"' in html),
        ("toggle script", "toggleFolderHit" in html),
        ("script in page", "initFolderTree" in html),
        ("no bootstrap collapse toggle", 'data-bs-toggle="collapse"' not in html),
        ("no overflow-hidden card", 'overflow-hidden jp-nas-browse-card' not in html),
    ]
    failed = []
    for name, ok in checks:
        print(f"{'OK' if ok else 'FAIL'}: {name}")
        if not ok:
            failed.append(name)

    targets = re.findall(r'data-folder-target="#(jp-folder-kids-\d+)"', html)
    missing = [t for t in targets if f'id="{t}"' not in html]
    if missing:
        failed.append(f"missing targets: {missing[:3]}")
        print(f"FAIL: {len(missing)} missing targets")
    else:
        print(f"OK: {len(targets)} expand pairs")

    idx = html.find("data-folder-target=")
    if idx >= 0:
        print("SAMPLE:", html[idx : idx + 180].replace("\n", " "))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
