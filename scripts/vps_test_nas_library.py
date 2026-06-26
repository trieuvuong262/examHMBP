"""Smoke + integration test Thư viện → Tải NAS — chạy trước deploy."""
import io
import json
import os
import re
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

REQUIRED_ZIP = frozenset({
    "JustPlay-NAS-RaiDrive-Setup.bat",
    "JustPlay-NAS-RaiDrive-Setup.ps1",
    "JustPlay-NAS-Config.json",
    "HUONG-DAN.txt",
})
PS1_MARKERS = (
    "Get-ShareNameList",
    "Import-JustPlayNasConfig",
    "Merge-ShareNameLists",
    "Connect-JustPlayNasShare",
    "Test-JustPlayNasBundleReady",
)


def validate_zip_bundle(content: bytes, label: str) -> list[str]:
    failed = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = set(zf.namelist())
        missing = REQUIRED_ZIP - names
        if missing:
            return [f"{label}: zip missing {sorted(missing)}"]

        cfg = json.loads(zf.read("JustPlay-NAS-Config.json").decode("utf-8"))
        if not cfg.get("shares"):
            failed.append(f"{label}: config shares empty for {cfg.get('portal_username')}")
        for key in ("server", "port", "ldap_domain", "portal_username", "drive_letter"):
            if key not in cfg:
                failed.append(f"{label}: config missing {key}")

        ps1 = zf.read("JustPlay-NAS-RaiDrive-Setup.ps1")
        if not ps1.startswith(b"\xef\xbb\xbf"):
            failed.append(f"{label}: ps1 missing UTF-8 BOM")
        ps1_text = ps1.decode("utf-8-sig", errors="replace")
        if "__NAS_SHARES__" in ps1_text:
            failed.append(f"{label}: ps1 has __NAS_SHARES__ placeholder")
        for marker in PS1_MARKERS:
            if marker not in ps1_text:
                failed.append(f"{label}: ps1 missing {marker}")

        m = re.search(r"\$NasSharesCsv = '([^']*)'", ps1_text)
        if not m or not m.group(1).strip():
            failed.append(f"{label}: ps1 NasSharesCsv empty")
        elif cfg.get("shares"):
            ps1_shares = [x.strip() for x in m.group(1).split(",") if x.strip()]
            if ps1_shares != cfg["shares"]:
                failed.append(
                    f"{label}: share mismatch ps1={ps1_shares!r} json={cfg['shares']!r}"
                )

        bat = zf.read("JustPlay-NAS-RaiDrive-Setup.bat").decode("utf-8", errors="replace")
        if "-STA" not in bat:
            failed.append(f"{label}: bat missing -STA")

    if not failed:
        print(f"OK: zip bundle {label} shares={cfg.get('shares')}")
    return failed


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
        print(f"OK: zip size {len(zip_resp.content)} bytes")
        failed.extend(validate_zip_bundle(zip_resp.content, user.username))

    # Vuonglnt — user thuc te bao loi
    vuong = User.objects.filter(username__iexact='Vuonglnt').first()
    if vuong:
        vc = Client(HTTP_HOST=host)
        vc.force_login(vuong)
        vresp = vc.get(url_zip, HTTP_HOST=host)
        if vresp.status_code != 200:
            failed.append(f"Vuonglnt zip HTTP {vresp.status_code}")
        else:
            failed.extend(validate_zip_bundle(vresp.content, 'Vuonglnt'))
            from nas_storage.download_shares import nas_mount_shares_for_user
            expected = nas_mount_shares_for_user(vuong)
            if not expected:
                failed.append('Vuonglnt: nas_mount_shares_for_user empty on server')
            else:
                print(f'OK: Vuonglnt server shares={expected}')
    else:
        print('SKIP: Vuonglnt not in DB')

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
