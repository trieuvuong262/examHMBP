"""Smoke test Thư viện → Tải NAS trên VPS."""
import os
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
    url_page = reverse("documents:nas_download")
    url_zip = reverse("documents:nas_download_setup")
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("FAIL: no superuser")
        return 1

    failed = []
    client = Client(HTTP_HOST=host)

    anon = client.get(url_page, HTTP_HOST=host)
    if anon.status_code not in (302, 301):
        failed.append(f"anonymous page expected redirect, got {anon.status_code}")
    else:
        print(f"OK: anonymous redirect -> {anon.url}")

    client.force_login(user)
    resp = client.get(url_page, HTTP_HOST=host)
    print(f"Page: {resp.status_code} {url_page}")
    if resp.status_code != 200:
        failed.append(f"page HTTP {resp.status_code}")
        print(resp.content[:500])
    else:
        html = resp.content.decode("utf-8", errors="replace")
        for marker in (
            "Tải NAS (Windows)",
            "không cần cài hay cấu hình RaiDrive",
            "tai-nas/tai/",
            "JustPlay-NAS-RaiDrive-Setup",
        ):
            if marker not in html:
                failed.append(f"page missing: {marker}")
            else:
                print(f"OK: page contains {marker!r}")

    zip_resp = client.get(url_zip, HTTP_HOST=host)
    print(f"ZIP: {zip_resp.status_code} {url_zip}")
    if zip_resp.status_code != 200:
        failed.append(f"zip HTTP {zip_resp.status_code}")
    elif zip_resp.get("Content-Type", "").split(";")[0] != "application/zip":
        failed.append(f"zip content-type {zip_resp.get('Content-Type')}")
    else:
        data = zip_resp.content
        print(f"OK: zip size {len(data)} bytes")
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            for name in (
                "JustPlay-NAS-RaiDrive-Setup.bat",
                "JustPlay-NAS-RaiDrive-Setup.ps1",
                "JustPlay-NAS-Config.json",
                "HUONG-DAN.txt",
            ):
                if name not in names:
                    failed.append(f"zip missing {name}")
                else:
                    print(f"OK: zip has {name}")
            ps1 = zf.read("JustPlay-NAS-RaiDrive-Setup.ps1")
            if not ps1.startswith(b"\xef\xbb\xbf"):
                failed.append("ps1 missing UTF-8 BOM")
            else:
                print("OK: ps1 UTF-8 BOM")
            ps1_text = ps1.decode("utf-8-sig", errors="replace")
            if "Import-JustPlayNasConfig" not in ps1_text:
                failed.append("ps1 missing config loader")
            else:
                print("OK: ps1 config loader")
            cfg_raw = zf.read("JustPlay-NAS-Config.json")
            import json as _json
            bundle = _json.loads(cfg_raw.decode("utf-8"))
            if not bundle.get("shares"):
                failed.append("config.json missing shares")
            elif bundle.get("portal_username") in (None, ""):
                failed.append("config.json missing portal_username")
            else:
                print("OK: config.json", bundle.get("portal_username"), bundle.get("shares"))

    folder_resp = client.get(reverse("nas_storage:folder_list"), HTTP_HOST=host)
    if folder_resp.status_code != 200:
        failed.append(f"folder_list HTTP {folder_resp.status_code}")
    else:
        fh = folder_resp.content.decode("utf-8", errors="replace")
        if "toggleFolderHit" not in fh:
            failed.append("folder_list missing toggleFolderHit")
        else:
            print("OK: folder_list expand JS present")

    print(f"NAS_RDRIVE_SERVER={getattr(settings, 'NAS_RDRIVE_SERVER', '?')}")
    print(f"NAS_RDRIVE_PORT={getattr(settings, 'NAS_RDRIVE_PORT', '?')}")

    if failed:
        print("--- FAILURES ---")
        for item in failed:
            print(" -", item)
        return 1
    print("--- ALL CHECKS PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
