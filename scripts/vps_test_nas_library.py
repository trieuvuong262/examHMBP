"""Smoke test — Windows ZIP + Ubuntu DEB tách riêng."""
import io
import json
import os
import sys
import zipfile

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
    if host == "*":
        host = "testserver"
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("FAIL: no superuser")
        return 1

    failed = []
    client = Client(HTTP_HOST=host)
    client.force_login(user)

    page = client.get(reverse("documents:nas_download"), HTTP_HOST=host)
    if page.status_code != 200:
        failed.append(f"page HTTP {page.status_code}")
    else:
        html = page.content.decode("utf-8", errors="replace")
        for m in ("Windows", "Ubuntu", ".deb", "windows_zip_url", "Tải Windows", "Tải Ubuntu"):
            # template uses urls not variable names in HTML
            pass
        for m in ("Tải Windows", "Tải Ubuntu", ".deb"):
            if m not in html:
                failed.append(f"page missing {m!r}")
            else:
                print(f"OK: page {m!r}")

    # Windows ZIP
    wz = client.get(reverse("documents:nas_download_setup") + "?os=win", HTTP_HOST=host)
    print(f"Windows ZIP: {wz.status_code}")
    if wz.status_code != 200:
        failed.append(f"win zip HTTP {wz.status_code}")
    else:
        with zipfile.ZipFile(io.BytesIO(wz.content)) as zf:
            names = set(zf.namelist())
            print("WIN files:", sorted(names))
            for req in (
                "Ket-Noi-NAS-JustPlay.exe",
                "JustPlay-NAS-Config.json",
                "Chay-Ket-Noi-NAS.bat",
            ):
                if req not in names:
                    failed.append(f"win zip missing {req}")
            for banned in (
                "JustPlay-RustDesk-Setup.sh",
                "JustPlay-Equipment-Scan.sh",
                "JustPlay-RaiDrive-Setup.sh",
            ):
                if banned in names:
                    failed.append(f"win zip still has ubuntu file {banned}")
            cfg = json.loads(zf.read("JustPlay-NAS-Config.json"))
            if cfg.get("bundle_kind") != "it_tools_windows":
                failed.append(f"win bundle_kind={cfg.get('bundle_kind')}")
            else:
                print("OK: win bundle_kind")
            if "JustPlay-Cong-Cu-IT-Windows.zip" not in (wz.get("Content-Disposition") or ""):
                failed.append(f"win filename {wz.get('Content-Disposition')}")

    # Ubuntu DEB
    ud = client.get(reverse("documents:nas_download_setup") + "?os=linux", HTTP_HOST=host)
    print(f"Ubuntu DEB: {ud.status_code} size={len(ud.content)}")
    if ud.status_code != 200:
        failed.append(f"ubuntu deb HTTP {ud.status_code} {ud.content[:120]!r}")
    else:
        if not ud.content.startswith(b"!<arch>\n"):
            failed.append("ubuntu deb missing ar magic")
        else:
            print("OK: deb ar magic")
        cd = ud.get("Content-Disposition") or ""
        if ".deb" not in cd:
            failed.append(f"ubuntu filename {cd}")
        else:
            print("OK: deb filename", cd)
        # crude: data.tar.gz member should exist in ar
        if b"data.tar.gz" not in ud.content[:500] and b"data.tar.gz" not in ud.content:
            # member name is in headers
            if b"data.tar.gz" not in ud.content:
                failed.append("deb missing data.tar.gz member name")
            else:
                print("OK: data.tar.gz present")
        else:
            print("OK: data.tar.gz present")

    if failed:
        print("--- FAILURES ---")
        for f in failed:
            print(" -", f)
        return 1
    print("--- ALL CHECKS PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
