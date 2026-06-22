"""Kiểm tra GET từng link module /thiet-bi/ — chạy trên VPS."""
import os
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import NoReverseMatch, reverse

from equipment.models import Device, DeviceCategory
from service_requests.models import RequestType, ServiceRequest

OK = {200, 301, 302, 303, 307, 308}
SKIP_GET = {
    "delete_bulk_devices_it",
    "delete_bulk_devices_production",
    "delete_bulk_devices",
    "category_delete_it",
    "category_delete_production",
    "category_delete",
    "import_devices_it",
    "import_devices_production",
    "import_devices",
}


def _user():
    return (
        get_user_model()
        .objects.filter(is_superuser=True, is_active=True)
        .order_by("id")
        .first()
    )


def _sample_device():
    return Device.objects.order_by("-updated_at").first()


def _sample_category():
    return DeviceCategory.objects.order_by("pk").first()


def _sample_repair_request_id():
    return (
        ServiceRequest.objects.filter(
            request_type__code=RequestType.CODE_IT_REPAIR,
        )
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )


def _url_specs():
    device = _sample_device()
    cat = _sample_category()
    req_id = _sample_repair_request_id()
    qr_key = device.device_code if device and device.device_code else None

    names = [
        "dashboard",
        "dashboard_it",
        "dashboard_production",
        "device_list_it",
        "device_list_production",
        "device_list",
        "device_add_it",
        "device_add_production",
        "device_add",
        "it_repair_list_it",
        "it_repair_list_production",
        "it_repair_list",
        "import_export_hub_it",
        "import_export_hub_production",
        "import_export_hub",
        "category_list_it",
        "category_list_production",
        "category_list",
        "category_add_it",
        "category_add_production",
        "category_add",
        "export_devices_it",
        "export_devices_production",
        "export_devices",
        "download_sample_it",
        "download_sample_production",
        "download_sample",
    ]

    specs = [(n, ()) for n in names]

    if cat:
        specs += [
            ("category_edit_it", (cat.pk,)),
            ("category_edit_production", (cat.pk,)),
            ("category_edit", (cat.pk,)),
        ]

    if req_id is not None:
        specs += [
            ("it_repair_detail_it", (req_id,)),
            ("it_repair_detail_production", (req_id,)),
            ("it_repair_detail", (req_id,)),
        ]

    if device:
        specs += [
            ("device_detail_manage", (device.pk,)),
            ("device_edit", (device.pk,)),
            ("device_history", (device.pk,)),
            ("device_update_history", (device.pk,)),
        ]
        if qr_key:
            specs.append(("device_qr_public", (qr_key,)))

    return specs


def main():
    user = _user()
    if not user:
        print("ERROR: no superuser")
        return 1

    client = Client(HTTP_HOST="portal.justplay.vn", secure=True)
    client.force_login(user)

    failed = []
    skipped = []
    ok_count = 0

    print(f"User: {user.username}\n")
    print(f"{'STATUS':<6} {'CODE':<4} {'URL NAME':<35} PATH")
    print("-" * 90)

    for name, args in _url_specs():
        if name in SKIP_GET:
            skipped.append(name)
            continue
        try:
            path = reverse(f"equipment:{name}", args=args)
        except NoReverseMatch as exc:
            print(f"FAIL   ---- {name:<35} NoReverseMatch: {exc}")
            failed.append((name, str(exc)))
            continue

        try:
            resp = client.get(path, follow=True)
            code = resp.status_code
            final = resp.request.get("PATH_INFO", path)
            if code >= 500:
                print(f"FAIL   {code:<4} {name:<35} {final}")
                snippet = resp.content[:800].decode("utf-8", errors="replace")
                failed.append((name, f"HTTP {code}", snippet))
            elif code not in OK:
                print(f"WARN   {code:<4} {name:<35} {final}")
                failed.append((name, f"HTTP {code}", ""))
            else:
                print(f"OK     {code:<4} {name:<35} {final}")
                ok_count += 1
        except Exception as exc:
            print(f"EXC    ---- {name:<35} {exc}")
            failed.append((name, str(exc), traceback.format_exc()[:500]))

    print("-" * 90)
    print(f"OK: {ok_count} | Failed/Warn: {len(failed)} | Skipped POST-only: {len(skipped)}")
    if failed:
        print("\n=== CHI TIẾT LỖI ===")
        for item in failed:
            print(f"\n--- {item[0]} ---")
            for part in item[1:]:
                if part:
                    print(part[:1200])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
