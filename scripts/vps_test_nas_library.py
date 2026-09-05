"""Smoke + integration test Thư viện → Tải bộ cài (Công cụ IT) — chạy trước deploy."""
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

REQUIRED_ZIP = frozenset({
    "Ket-Noi-NAS-JustPlay.exe",
    "JustPlay-NAS-Config.json",
    "Mo-Ket-Noi-NAS.ps1",
    "Chay-Ket-Noi-NAS.bat",
    "KET-NOI-NAS.bat",
})
OPTIONAL_ZIP = frozenset({
    "JustPlay-RustDesk-Setup.ps1",
    "JustPlay-RustDesk-Setup.sh",
    "JustPlay-Equipment-Scan.ps1",
})


def validate_zip_bundle(content: bytes, label: str) -> list[str]:
    failed = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = set(zf.namelist())
        missing = REQUIRED_ZIP - names
        if missing:
            return [f"{label}: zip missing {sorted(missing)}"]

        cfg = json.loads(zf.read("JustPlay-NAS-Config.json").decode("utf-8"))
        if cfg.get("bundle_kind") != "it_tools":
            failed.append(f"{label}: expected bundle_kind=it_tools, got {cfg.get('bundle_kind')!r}")
        if not cfg.get("portal_username"):
            failed.append(f"{label}: config missing portal_username")
        if not cfg.get("has_rustdesk") and not cfg.get("has_equipment_scan"):
            failed.append(f"{label}: config has no IT tools flags")

        extra = names - REQUIRED_ZIP - OPTIONAL_ZIP
        if extra:
            failed.append(f"{label}: zip has unexpected files {sorted(extra)}")

        # Không còn đóng gói script kết nối NAS
        for banned in (
            "JustPlay-NAS-RaiDrive-Setup.ps1",
            "Prepare-JustPlay-WebClient.ps1",
        ):
            if banned in names:
                failed.append(f"{label}: zip still contains NAS connect file {banned}")

        exe_data = zf.read("Ket-Noi-NAS-JustPlay.exe")
        if len(exe_data) < 8192:
            failed.append(f"{label}: exe too small ({len(exe_data)} bytes)")
        elif exe_data[:2] != b"MZ":
            failed.append(f"{label}: exe missing MZ header")

        if cfg.get("has_rustdesk") and "JustPlay-RustDesk-Setup.ps1" not in names:
            failed.append(f"{label}: config has_rustdesk but zip missing ps1")
        if cfg.get("has_rustdesk") and "JustPlay-RustDesk-Setup.sh" not in names:
            failed.append(f"{label}: config has_rustdesk but zip missing ubuntu .sh")
        if cfg.get("has_equipment_scan") and "JustPlay-Equipment-Scan.ps1" not in names:
            failed.append(f"{label}: config has_equipment_scan but zip missing ps1")
        if not cfg.get("has_rustdesk") and not cfg.get("has_equipment_scan"):
            failed.append(f"{label}: no IT tool scripts expected")
        elif (
            "JustPlay-RustDesk-Setup.ps1" not in names
            and "JustPlay-RustDesk-Setup.sh" not in names
            and "JustPlay-Equipment-Scan.ps1" not in names
        ):
            failed.append(f"{label}: zip missing both IT tool scripts")

        if "JustPlay-RustDesk-Setup.ps1" in names:
            rd = zf.read("JustPlay-RustDesk-Setup.ps1").decode("utf-8-sig", errors="replace")
            if "__ENROLL_SECRET__" in rd or "__PUBLIC_KEY__" in rd:
                failed.append(f"{label}: rustdesk ps1 has placeholders")
        if "JustPlay-RustDesk-Setup.sh" in names:
            sh = zf.read("JustPlay-RustDesk-Setup.sh").decode("utf-8", errors="replace")
            if "__ENROLL_SECRET__" in sh or "__PUBLIC_KEY__" in sh:
                failed.append(f"{label}: rustdesk ubuntu sh has placeholders")
            if "Ubuntu 26.04" not in sh:
                failed.append(f"{label}: ubuntu sh missing Ubuntu 26.04 banner")
        if "JustPlay-Equipment-Scan.ps1" in names:
            eq = zf.read("JustPlay-Equipment-Scan.ps1").decode("utf-8-sig", errors="replace")
            if "__SCAN_SECRET__" in eq:
                failed.append(f"{label}: equipment ps1 has placeholders")

    if not failed:
        tools = []
        if cfg.get("has_rustdesk"):
            tools.append("rustdesk")
        if cfg.get("has_equipment_scan"):
            tools.append("equipment")
        print(f"OK: zip bundle {label} tools={tools}")
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
            "Tải bộ cài",
            "Công cụ IT",
            "tai-nas/tai/",
        ):
            if marker not in html:
                failed.append(f"page missing: {marker}")
            else:
                print(f"OK: page contains {marker!r}")
        if "Kết nối NAS" in html or "ổ đĩa dự kiến" in html.lower():
            failed.append("page still mentions NAS connect")

    zip_resp = client.get(url_zip, HTTP_HOST=host)
    print(f"ZIP: {zip_resp.status_code} {url_zip}")
    if zip_resp.status_code == 404:
        print("SKIP/WARN: zip 404 — chưa cấu hình RustDesk/equipment secrets?")
        # Không fail cứng nếu môi trường test thiếu secret; chỉ báo
        body = zip_resp.content.decode("utf-8", errors="replace")
        if "Chưa cấu hình" not in body and "launcher" not in body.lower():
            failed.append(f"zip HTTP 404 unexpected body: {body[:200]}")
    elif zip_resp.status_code != 200:
        failed.append(f"zip HTTP {zip_resp.status_code}")
    elif zip_resp.get("Content-Type", "").split(";")[0] != "application/zip":
        failed.append(f"zip content-type {zip_resp.get('Content-Type')}")
    else:
        cd = zip_resp.get("Content-Disposition", "")
        if "JustPlay-Cong-Cu-IT.zip" not in cd:
            failed.append(f"zip filename unexpected: {cd}")
        print(f"OK: zip size {len(zip_resp.content)} bytes")
        failed.extend(validate_zip_bundle(zip_resp.content, user.username))

    vuong = User.objects.filter(username__iexact='Vuonglnt').first()
    if vuong:
        vc = Client(HTTP_HOST=host)
        vc.force_login(vuong)
        vresp = vc.get(url_zip, HTTP_HOST=host)
        if vresp.status_code == 200:
            failed.extend(validate_zip_bundle(vresp.content, 'Vuonglnt'))
        elif vresp.status_code == 404:
            print('SKIP: Vuonglnt zip 404 (missing IT secrets?)')
        else:
            failed.append(f"Vuonglnt zip HTTP {vresp.status_code}")
    else:
        print('SKIP: Vuonglnt not in DB')

    if failed:
        print("--- FAILURES ---")
        for item in failed:
            print(" -", item)
        return 1
    print("--- ALL CHECKS PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
